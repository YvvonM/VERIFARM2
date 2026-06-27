"use client";

// Ported from chris-frontend (App.tsx): the VeriFarm login screen — dark-green
// glassmorphism, ambient radial glows, hero panel + sign-in form.
import { useState } from "react";
import { motion } from "motion/react";
import { Shield } from "lucide-react";

import { ImageWithFallback } from "@/components/figma/ImageWithFallback";

const heroPhoto = "/verifarm-hero.png";

// ── Brand ──────────────────────────────────────────────────────────────────
const G_VIB = "#4ADE80";

// ── Glassmorphism helper ─────────────────────────────────────────────────────
const gl = (alpha = 0.05, blur = 20): React.CSSProperties => ({
  background: `rgba(255,255,255,${alpha})`,
  backdropFilter: `blur(${blur}px)`,
  WebkitBackdropFilter: `blur(${blur}px)`,
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 16,
  boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
});

function AmbientBg() {
  return (
    <>
      <div style={{ position: "fixed", top: "-20%", left: "-10%", width: 700, height: 700, borderRadius: "50%", background: "radial-gradient(circle, rgba(11,110,79,0.22) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />
      <div style={{ position: "fixed", bottom: "-20%", right: "-10%", width: 600, height: 600, borderRadius: "50%", background: "radial-gradient(circle, rgba(124,58,237,0.16) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />
      <div style={{ position: "fixed", top: "45%", left: "55%", width: 400, height: 400, borderRadius: "50%", background: "radial-gradient(circle, rgba(244,162,97,0.08) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />
    </>
  );
}

export interface LoginPageProps {
  /** Called with the chosen role ("officer" | "farmer") on sign-in. */
  onLogin: (role: string) => void;
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const [email, setEmail] = useState("grace.mwangi@kcb.co.ke");
  const [password, setPassword] = useState("••••••••");

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "11px 14px", borderRadius: 10,
    background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.12)",
    color: "#fff", fontSize: 14, outline: "none", fontFamily: "'Inter', sans-serif",
  };

  return (
    <div style={{ minHeight: "100vh", position: "relative", overflow: "hidden" }}>
      <AmbientBg />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6 }}
        style={{ position: "relative", zIndex: 1, minHeight: "100vh", display: "grid", gridTemplateColumns: "repeat(2,1fr)" }}
      >
        {/* Left: hero panel */}
        <div className="relative hidden md:flex flex-col justify-between p-10" style={{ overflow: "hidden" }}>
          <ImageWithFallback
            src={heroPhoto}
            alt="Farmer using a tablet in a field with smart agriculture technology overlay"
            className="absolute inset-0 w-full h-full object-cover"
          />
          <div className="absolute inset-0" style={{ background: "linear-gradient(140deg, rgba(5,16,14,0.93) 0%, rgba(11,30,22,0.75) 60%, rgba(7,20,14,0.85) 100%)" }} />
          <div className="relative z-10">
            <div className="flex items-center gap-2.5">
              <Shield size={18} style={{ color: G_VIB }} />
              <span style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: 20, letterSpacing: "0.08em" }}>VERIFARM</span>
            </div>
          </div>
          <div className="relative z-10">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.6 }}>
              <h2 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "2.8rem", lineHeight: 1.1, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 12 }}>
                Verified Data.<br />Stronger<br />Farmers.
              </h2>
              <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.55)", fontSize: "1.25rem", marginBottom: 28 }}>
                Turning fragmented records into fundable profiles.
              </p>
              <div className="flex gap-7">
                {[
                  { val: "12,400+", sub: "Farmers verified" },
                  { val: "94%", sub: "Data accuracy" },
                  { val: "3.2×", sub: "Faster decisions" },
                ].map(({ val, sub }) => (
                  <div key={sub}>
                    <p style={{ fontFamily: "'Anton', sans-serif", color: G_VIB, fontSize: "1.4rem" }}>{val}</p>
                    <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "0.95rem" }}>{sub}</p>
                  </div>
                ))}
              </div>
            </motion.div>
          </div>
        </div>

        {/* Right: login form */}
        <div className="flex items-center justify-center p-8" style={{ background: "rgba(5,16,14,0.7)", backdropFilter: "blur(20px)" }}>
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15, duration: 0.55, ease: "easeOut" }}
            style={{ ...gl(0.07, 24), padding: "40px 36px", width: "100%", maxWidth: 380 }}
          >
            <div className="md:hidden flex items-center gap-2 mb-8">
              <Shield size={18} style={{ color: G_VIB }} />
              <span style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: 20, letterSpacing: "0.08em" }}>VERIFARM</span>
            </div>

            <h2 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.7rem", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
              Welcome Back
            </h2>
            <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "1.15rem", marginBottom: 28 }}>
              Sign in to continue to VeriFarm
            </p>

            <div className="space-y-4">
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "rgba(255,255,255,0.55)", marginBottom: 6, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                  Email address
                </label>
                <input value={email} onChange={(e) => setEmail(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "rgba(255,255,255,0.55)", marginBottom: 6, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                  Password
                </label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={inputStyle} />
              </div>
            </div>

            <motion.button
              onClick={() => onLogin("officer")}
              whileHover={{ scale: 1.02, boxShadow: `0 0 28px ${G_VIB}45` }}
              whileTap={{ scale: 0.98 }}
              style={{ width: "100%", marginTop: 24, padding: "13px 0", borderRadius: 12, background: G_VIB, color: "#071410", fontWeight: 700, fontSize: 14, border: "none", cursor: "pointer", boxShadow: `0 0 20px ${G_VIB}30` }}
            >
              Sign in as Credit Officer
            </motion.button>

            <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "20px 0" }}>
              <div style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.08)" }} />
              <span style={{ fontSize: 12, color: "rgba(255,255,255,0.25)" }}>or</span>
              <div style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.08)" }} />
            </div>

            <motion.button
              onClick={() => onLogin("farmer")}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              style={{ width: "100%", padding: "12px 0", borderRadius: 12, background: "transparent", color: "rgba(255,255,255,0.6)", fontSize: 14, border: "1px solid rgba(255,255,255,0.12)", cursor: "pointer" }}
            >
              Continue as Farmer (Mary Wanjiku)
            </motion.button>

            <p style={{ textAlign: "center", marginTop: 24, fontSize: 11, color: "rgba(255,255,255,0.2)", fontFamily: "'Caveat', cursive" }}>
              Verified Data · Better Decisions · Stronger Farmers
            </p>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
}

export default LoginPage;
