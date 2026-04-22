/**
 * Migration: Reset scan counts for all users on server start.
 * This fixes existing users who have scanCount from the old system
 * but no scanCountResetAt set (daily resets didn't exist before).
 */
async function migrateScanCounts() {
	const User = require("../models/User");
	const Plan = require("../models/Plan");

	try {
		// Find all users who have scans used but no reset timestamp
		const usersWithoutReset = await User.find({
			scanCount: { $gt: 0 },
			$or: [
				{ scanCountResetAt: null },
				{ scanCountResetAt: { $exists: false } },
			],
		});

		if (usersWithoutReset.length === 0) {
			console.log("Migration: No stale scan counts found.");
			return;
		}

		console.log(
			`Migration: Resetting scan counts for ${usersWithoutReset.length} users...`,
		);

		// Get default plan scan limit
		const defaultPlan = await Plan.findOne({
			isDefault: true,
			isActive: true,
		}).lean();
		const defaultLimit = defaultPlan ? defaultPlan.scansPerDay : 5;

		// Get each user's plan limit
		await Promise.all(
			usersWithoutReset.map(async (user) => {
				let planLimit = defaultLimit;
				if (user.planId) {
					const plan = await Plan.findById(user.planId).lean();
					if (plan && plan.isActive) planLimit = plan.scansPerDay;
				}
				// Also check dailyScanLimit override
				if (user.dailyScanLimit != null)
					planLimit = user.dailyScanLimit;

				// Ensure planLimit is a valid number
				planLimit = Number.isFinite(planLimit)
					? planLimit
					: defaultLimit;

				// If user's scanCount <= their plan limit, just set reset time (they can still scan today)
				if (user.scanCount <= planLimit) {
					await User.findByIdAndUpdate(user._id, {
						scanCountResetAt: new Date(),
					});
					console.log(
						`  ${user.email}: scanCount=${user.scanCount} <= limit=${planLimit} → just reset timestamp`,
					);
				} else {
					// If scanCount > plan limit (old system overflow), set count to limit
					await User.findByIdAndUpdate(user._id, {
						scanCount: planLimit,
						scanCountResetAt: new Date(),
					});
					console.log(
						`  ${user.email}: scanCount=${user.scanCount} > limit=${planLimit} → capped to ${planLimit}`,
					);
				}
			}),
		);

		console.log("Migration: Scan counts reset complete.");
	} catch (err) {
		console.error("Migration error:", err.message);
	}
}

module.exports = migrateScanCounts;
