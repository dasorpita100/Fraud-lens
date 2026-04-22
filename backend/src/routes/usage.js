const express = require("express");
const User = require("../models/User");
const Plan = require("../models/Plan");
const ScanHistory = require("../models/ScanHistory");
const { protect } = require("../middleware/auth");

const router = express.Router();

/** Check if a day has passed and reset scan count */
function shouldResetDaily(user) {
	if (!user.scanCountResetAt) return true;
	const now = new Date();
	const reset = new Date(user.scanCountResetAt);
	return (
		now.getFullYear() !== reset.getFullYear() ||
		now.getMonth() !== reset.getMonth() ||
		now.getDate() !== reset.getDate()
	);
}

/** Get effective scan limit for a user (from plan or default) */
async function getEffectiveScanLimit(user) {
	if (user.dailyScanLimit != null) return user.dailyScanLimit;
	if (user.planId) {
		const plan = await Plan.findById(user.planId).lean();
		if (plan && plan.isActive) return plan.scansPerDay;
	}
	const defaultPlan = await Plan.findOne({
		isDefault: true,
		isActive: true,
	}).lean();
	return defaultPlan ? defaultPlan.scansPerDay : 5;
}

/** GET /api/usage - current user's scan usage (protected) */
router.get("/", protect, async (req, res) => {
	try {
		const user = await User.findById(req.user.id).populate(
			"planId",
			"name slug scansPerDay price interval",
		);
		if (!user) {
			return res
				.status(404)
				.json({ success: false, message: "User not found." });
		}

		let scanCount = user.scanCount || 0;
		let needsSave = false;

		// Reset scan count if a new day has started
		if (shouldResetDaily(user)) {
			scanCount = 0;
			user.scanCount = 0;
			user.scanCountResetAt = new Date();
			needsSave = true;
		}

		// Save if needed
		if (needsSave) {
			await user.save({ validateBeforeSave: false });
		}

		const scanLimit = await getEffectiveScanLimit(user);
		const canScan = scanCount < scanLimit;

		res.json({
			success: true,
			data: {
				scanCount,
				scanLimit,
				canScan,
				credits: user.credits || 0,
				plan: user.planId || null,
				resetAt: user.scanCountResetAt,
			},
		});
	} catch (err) {
		console.error("Usage get error:", err);
		res.status(500).json({ success: false, message: "Server error." });
	}
});

/** GET /api/usage/scans - paginated scan history (protected) */
router.get("/scans", protect, async (req, res) => {
	try {
		const raw = parseInt(String(req.query.limit || "100"), 10);
		const limit = Math.min(
			200,
			Math.max(1, Number.isFinite(raw) ? raw : 100),
		);
		const page = Math.max(1, parseInt(String(req.query.page || "1"), 10));
		const skip = (page - 1) * limit;

		const [scans, total] = await Promise.all([
			ScanHistory.find({ user: req.user.id })
				.sort({ createdAt: -1 })
				.skip(skip)
				.limit(limit)
				.lean(),
			ScanHistory.countDocuments({ user: req.user.id }),
		]);

		res.json({
			success: true,
			data: { scans, total, page, totalPages: Math.ceil(total / limit) },
		});
	} catch (err) {
		console.error("Usage scans list error:", err);
		res.status(500).json({ success: false, message: "Server error." });
	}
});

/** GET /api/usage/scans/:id - get single scan detail (protected) */
router.get("/scans/:id", protect, async (req, res) => {
	try {
		const scan = await ScanHistory.findOne({
			_id: req.params.id,
			user: req.user.id,
		}).lean();
		if (!scan) {
			return res
				.status(404)
				.json({ success: false, message: "Scan not found." });
		}
		res.json({ success: true, data: { scan } });
	} catch (err) {
		console.error("Usage scan detail error:", err);
		res.status(500).json({ success: false, message: "Server error." });
	}
});

/** POST /api/usage/record-scan - record one scan (protected), returns updated usage */
router.post("/record-scan", protect, async (req, res) => {
	try {
		const user = await User.findById(req.user.id);
		if (!user) {
			return res
				.status(404)
				.json({ success: false, message: "User not found." });
		}

		const scanLimit = await getEffectiveScanLimit(user);
		if (shouldResetDaily(user)) {
			user.scanCount = 0;
			user.scanCountResetAt = new Date();
		}

		const current = user.scanCount || 0;
		if (current >= scanLimit) {
			return res.status(403).json({
				success: false,
				message:
					"Daily scan limit reached. Please upgrade your plan or purchase credits.",
				data: { scanCount: current, scanLimit, canScan: false },
			});
		}

		user.scanCount = current + 1;
		await user.save({ validateBeforeSave: false });

		const body = req.body && typeof req.body === "object" ? req.body : {};
		const scanType = String(body.scanType || "").toLowerCase();
		if (["email", "sms", "upi"].includes(scanType)) {
			try {
				const scanData = {
					user: user._id,
					scanType,
					verdict: String(body.verdict || "").slice(0, 120),
					score: Math.min(100, Math.max(0, Number(body.score) || 0)),
					preview: String(
						body.contentPreview || body.preview || "",
					).slice(0, 500),
				};
				if (body.content)
					scanData.content = String(body.content).slice(0, 10000);
				if (body.imageData)
					scanData.imageData = String(body.imageData).slice(
						0,
						500000,
					);
				if (body.extractedText)
					scanData.extractedText = String(body.extractedText).slice(
						0,
						5000,
					);
				if (body.parsedFields)
					scanData.parsedFields = body.parsedFields;
				if (body.explanation)
					scanData.explanation = String(body.explanation).slice(
						0,
						3000,
					);
				if (Array.isArray(body.reasons))
					scanData.reasons = body.reasons.slice(0, 20);

				await ScanHistory.create(scanData);
			} catch (histErr) {
				console.error("Scan history save:", histErr.message);
			}
		}

		const newLimit = await getEffectiveScanLimit(user);
		res.json({
			success: true,
			message: "Scan recorded.",
			data: {
				scanCount: user.scanCount,
				scanLimit: newLimit,
				canScan: user.scanCount < newLimit,
				credits: user.credits || 0,
			},
		});
	} catch (err) {
		console.error("Record scan error:", err);
		res.status(500).json({ success: false, message: "Server error." });
	}
});

/** POST /api/usage/add-credits - mock credit purchase (protected) */
router.post("/add-credits", protect, async (req, res) => {
	try {
		const { amount, credits } = req.body || {};
		if (!amount || !credits || credits <= 0) {
			return res
				.status(400)
				.json({ success: false, message: "Invalid credit amount." });
		}
		const user = await User.findById(req.user.id);
		if (!user) {
			return res
				.status(404)
				.json({ success: false, message: "User not found." });
		}
		user.credits = (user.credits || 0) + Number(credits);
		await user.save({ validateBeforeSave: false });

		const Payment = require("../models/Payment");
		const payment = await Payment.create({
			user: user._id,
			amount: Number(amount),
			credits: Number(credits),
			creditsAdded: Number(credits),
			status: "completed",
			paymentMethod: "mock_upi",
			description: `Added ${credits} mock credits`,
			transactionId:
				"MOCK-CR-" +
				Date.now() +
				"-" +
				Math.random().toString(36).substr(2, 6).toUpperCase(),
		});

		res.json({
			success: true,
			message: `${credits} credits added to your account.`,
			data: { credits: user.credits, paymentId: payment._id },
		});
	} catch (err) {
		console.error("Add credits error:", err);
		res.status(500).json({ success: false, message: "Server error." });
	}
});

module.exports = router;
