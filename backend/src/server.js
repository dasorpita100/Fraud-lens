require("dotenv").config();
const express = require("express");
const cors = require("cors");
const rateLimit = require("express-rate-limit");
const connectDB = require("./config/db");

const authRoutes = require("./routes/auth");
const dashboardRoutes = require("./routes/dashboard");
const adminUsersRoutes = require("./routes/adminUsers");
const adminPlansRoutes = require("./routes/adminPlans");
const adminPaymentsRoutes = require("./routes/adminPayments");
const adminContactsRoutes = require("./routes/adminContacts");
const usageRoutes = require("./routes/usage");
const plansRoutes = require("./routes/plans");
const contactRoutes = require("./routes/contact");
const geminiExplainRoutes = require("./routes/geminiExplain");
const scanRoutes = require("./routes/scan");
const Plan = require("./models/Plan");
const migrateScanCounts = require("./migrations/resetScanCounts");

connectDB();

// Ensure default plans exist
async function seedDefaultPlans() {
	try {
		const defaults = [
			{
				name: "Free",
				slug: "free",
				scansPerDay: 5,
				price: 0,
				interval: "free",
				isDefault: true,
				isActive: true,
				sortOrder: 0,
			},
			{
				name: "Basic",
				slug: "basic",
				scansPerDay: 10,
				price: 99,
				interval: "monthly",
				isActive: true,
				sortOrder: 1,
			},
			{
				name: "Pro",
				slug: "pro",
				scansPerDay: 10,
				price: 199,
				interval: "monthly",
				isActive: true,
				sortOrder: 2,
			},
		];
		for (const p of defaults) {
			const exists = await Plan.findOne({ slug: p.slug });
			if (!exists) await Plan.create(p);
		}
		console.log("Default plans seeded.");
	} catch (e) {
		console.error("Seed plans:", e.message);
	}
}

// Run migration and seed plans on server start
setTimeout(async () => {
	await seedDefaultPlans();
	await migrateScanCounts();
}, 1000);

const app = express();

const authLimiter = rateLimit({
	windowMs: 15 * 60 * 1000,
	max: 20,
	message: { success: false, message: "Too many attempts. Try again later." },
});
app.use("/api/auth/login", authLimiter);
app.use("/api/auth/register", authLimiter);

app.use(express.json({ limit: "10mb" }));
app.use(express.urlencoded({ extended: true, limit: "10mb" }));

const corsOptions = {
	origin: process.env.CORS_ORIGIN || "http://localhost:3000",
	credentials: true,
};
app.use(cors(corsOptions));

app.use("/api/auth", authRoutes);
app.use("/api/dashboard", dashboardRoutes);
app.use("/api/admin/users", adminUsersRoutes);
app.use("/api/admin/plans", adminPlansRoutes);
app.use("/api/admin/payments", adminPaymentsRoutes);
app.use("/api/admin/contacts", adminContactsRoutes);
app.use("/api/usage", usageRoutes);
app.use("/api/plans", plansRoutes);
app.use("/api/contact", contactRoutes);
app.use("/api/gemini", geminiExplainRoutes);
app.use("/api/scan", scanRoutes);

app.get("/api/health", (req, res) => {
	res.json({ success: true, message: "FraudLens API is running." });
});

app.use((req, res) => {
	res.status(404).json({ success: false, message: "Route not found." });
});

app.use((err, req, res, next) => {
	console.error(err);
	res.status(500).json({ success: false, message: "Server error." });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
	console.log(`FraudLens backend running on port ${PORT}`);
});
