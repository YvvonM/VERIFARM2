import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Shield, UserCheck, MapPin, Leaf, Sprout, Building2,
  CheckCircle2, XCircle, Clock, AlertTriangle, ArrowRight,
  Banknote, Umbrella, Package, Landmark, CreditCard,
  TrendingUp, ThumbsUp, ThumbsDown, ChevronDown, ChevronUp,
  Phone, Globe, BadgeCheck, Zap, FileText, Info
} from "lucide-react";

const G_VIB   = "#4ADE80";
const GOLD    = "#F4A261";
const PURPLE  = "#7C3AED";
const R_LIGHT = "#F87171";
const SKY     = "#38BDF8";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Icon map ────────────────────────────────────────────────────────────────
const ICON_MAP: Record<string, React.ElementType> = {
  Banknote, Umbrella, Package, Building2, Shield, CreditCard, Landmark,
};

// ── Glassmorphism ───────────────────────────────────────────────────────────
const gl = (alpha = 0.05, blur = 20): React.CSSProperties => ({
  background: `rgba(255,255,255,${alpha})`,
  backdropFilter: `blur(${blur}px)`,
  WebkitBackdropFilter: `blur(${blur}px)`,
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 16,
  boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
});

// ── Utilities ─────────────────────────────────────────────────────────────────
function vColor(s: string) {
  return s === "Verified" ? G_VIB : s === "Pending" ? GOLD : R_LIGHT;
}
function riskColor(n: number) {
  return n >= 70 ? G_VIB : n >= 50 ? GOLD : R_LIGHT;
}
function statusCfg(s: string) {
  if (s === "approved") return { color: G_VIB,  label: "Approved", Icon: CheckCircle2 };
  if (s === "rejected") return { color: R_LIGHT, label: "Rejected", Icon: XCircle };
  return { color: GOLD, label: "Pending Review", Icon: Clock };
}

// ── Avatar ────────────────────────────────────────────────────────────────────
function Avatar({ name, size = 52, color = G_VIB }: { name: string; size?: number; color?: string }) {
  const initials = name.trim().split(/\s+/).map(w => w[0]?.toUpperCase() ?? "").slice(0, 2).join("");
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%", flexShrink: 0,
      background: `${color}18`, border: `1.5px solid ${color}35`,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <span style={{ fontFamily: "'Anton', sans-serif", fontSize: size * 0.34, color, letterSpacing: "0.02em" }}>
        {initials}
      </span>
    </div>
  );
}

// ── Risk Ring ─────────────────────────────────────────────────────────────────
function RiskRing({ score }: { score: number }) {
  const c = riskColor(score);
  const label = score >= 70 ? "Low Risk" : score >= 50 ? "Medium Risk" : "High Risk";
  const circumference = 2 * Math.PI * 28;
  const dash = (score / 100) * circumference;

  return (
    <div className="flex items-center gap-4">
      <div className="relative w-20 h-20 shrink-0">
        <svg width="80" height="80" className="-rotate-90">
          <circle cx="40" cy="40" r="28" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
          <motion.circle
            cx="40" cy="40" r="28" fill="none"
            stroke={c} strokeWidth="5" strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: circumference - dash }}
            transition={{ duration: 1, ease: "easeOut", delay: 0.3 }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono font-bold text-xl leading-none text-white">{score}</span>
          <span className="text-[8px] text-white/40 mt-0.5">/ 100</span>
        </div>
      </div>
      <div>
        <p className="font-semibold text-sm" style={{ color: c }}>{label}</p>
        <p className="text-xs mt-1 leading-relaxed" style={{ color: "rgba(255,255,255,0.45)" }}>
          Composite score from verified identity, land, production and credit data.
        </p>
      </div>
    </div>
  );
}

// ── Verification Badge ────────────────────────────────────────────────────────
function VerifBadge({ status }: { status: string }) {
  const c = vColor(status);
  const Icon = status === "Verified" ? CheckCircle2 : status === "Pending" ? Clock : XCircle;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold"
      style={{ background: `${c}18`, color: c, border: `1px solid ${c}30` }}>
      <Icon size={10} /> {status}
    </span>
  );
}

// ── Status Pill ───────────────────────────────────────────────────────────────
function StatusPill({ status }: { status: string }) {
  const { color, label, Icon } = statusCfg(status);
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold"
      style={{ background: `${color}18`, color, border: `1px solid ${color}30` }}>
      <Icon size={10} /> {label}
    </span>
  );
}

// ── Confidence Bar ────────────────────────────────────────────────────────────
function ConfidenceBar({ value, color = G_VIB }: { value: number; color?: string }) {
  if (!value && value !== 0) return <span className="text-xs italic" style={{ color: "rgba(255,255,255,0.3)" }}>No data</span>;
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
        <motion.div
          className="h-full rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
          style={{ background: color }}
        />
      </div>
      <span className="text-xs font-mono font-semibold shrink-0" style={{ color, minWidth: 34 }}>{pct}%</span>
    </div>
  );
}

// ── Conflict Comparison ───────────────────────────────────────────────────────
function ConflictComparison({ verifications }: { verifications: any[] }) {
  const conflicts = verifications.filter((v: any) => v.conflictsWithIds?.length > 0);
  if (!conflicts.length) return null;

  return (
    <div className="space-y-3 mt-3">
      {conflicts.map((v: any) => (
        <motion.div
          key={v.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-3 rounded-xl"
          style={{ background: `${R_LIGHT}08`, border: `1px solid ${R_LIGHT}20` }}
        >
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={12} style={{ color: R_LIGHT }} />
            <span className="text-[11px] font-bold" style={{ color: R_LIGHT }}>Conflict Detected</span>
          </div>
          <p className="text-xs mb-2" style={{ color: "rgba(255,255,255,0.5)" }}>
            Multiple sources reported different values for {v.type}.
          </p>
          <div className="grid grid-cols-2 gap-2">
            {verifications
              .filter((x: any) => x.claim_type === v.claim_type)
              .map((x: any, i: number) => (
                <div key={i} className="p-2 rounded-lg" style={{ background: "rgba(255,255,255,0.04)" }}>
                  <p className="text-[10px]" style={{ color: "rgba(255,255,255,0.4)" }}>{x.source}</p>
                  <p className="text-sm font-mono font-semibold text-white">{x.value || "—"}</p>
                  <ConfidenceBar value={x.confidence} color={vColor(x.status)} />
                </div>
              ))}
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ── Verification Card ─────────────────────────────────────────────────────────
function VerificationCard({ v, index }: { v: any; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const c = v.conflictsWithIds?.length ? R_LIGHT : vColor(v.status);
  const hasConflict = v.conflictsWithIds?.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.4 }}
      style={{ ...gl(0.04), border: `1px solid ${c}20`, padding: "16px 18px" }}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <Shield size={14} style={{ color: c }} />
          <div>
            <p className="font-semibold text-sm text-white">{v.type}</p>
            <p className="text-[10px]" style={{ color: "rgba(255,255,255,0.35)" }}>{v.source}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hasConflict && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold"
              style={{ background: `${R_LIGHT}15`, color: R_LIGHT, border: `1px solid ${R_LIGHT}30` }}>
              <AlertTriangle size={8} /> {v.conflictsWithIds.length} conflict{v.conflictsWithIds.length > 1 ? "s" : ""}
            </span>
          )}
          <VerifBadge status={v.status} />
        </div>
      </div>

      <div className="mt-3">
        <div className="flex items-center justify-between text-xs mb-1">
          <span style={{ color: "rgba(255,255,255,0.35)" }}>Confidence</span>
          <span className="font-mono font-semibold" style={{ color: c }}>
            {v.confidence > 0 ? `${Math.round(v.confidence * 100)}%` : "—"}
          </span>
        </div>
        <ConfidenceBar value={v.confidence} color={c} />
      </div>

      {v.value && (
        <div className="mt-3 pt-3" style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
          <div className="flex items-center justify-between">
            <span className="text-[10px]" style={{ color: "rgba(255,255,255,0.35)" }}>Recorded Value</span>
            <span className="text-xs font-mono text-white">{v.value}</span>
          </div>
        </div>
      )}

      {hasConflict && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[11px] font-medium"
            style={{ color: R_LIGHT, background: "none", border: "none", cursor: "pointer" }}
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {expanded ? "Hide details" : "View conflicting claims"}
          </button>
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.25 }}
                className="overflow-hidden"
              >
                <div className="mt-2 p-2 rounded-lg" style={{ background: `${R_LIGHT}06` }}>
                  <p className="text-[10px] mb-1.5" style={{ color: "rgba(255,255,255,0.4)" }}>
                    This claim conflicts with other verified sources. A credit officer must resolve this.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  );
}

// ── Offer Card ────────────────────────────────────────────────────────────────
function OfferCard({ offer, index, onApply }: { offer: any; index: number; onApply: (o: any) => void }) {
  const OfferIcon: React.ElementType = ICON_MAP[offer.Icon] ?? Package;
  const [applied, setApplied] = useState(false);

  const handleApply = () => {
    setApplied(true);
    onApply(offer);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.4 }}
      whileHover={{ y: -2, boxShadow: `0 20px 60px rgba(0,0,0,0.5), 0 0 0 1px ${offer.color}25` }}
      style={{ ...gl(0.06), padding: 20, cursor: "default" }}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div style={{
            width: 40, height: 40, borderRadius: 10,
            background: `${offer.color}15`, border: `1px solid ${offer.color}30`,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0
          }}>
            <OfferIcon size={18} style={{ color: offer.color }} />
          </div>
          <div>
            <p className="font-semibold text-sm text-white">{offer.type}</p>
            <p className="text-xs" style={{ color: "rgba(255,255,255,0.45)" }}>{offer.provider}</p>
          </div>
        </div>
        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
          style={{
            background: offer.eligible ? `${G_VIB}15` : `${GOLD}15`,
            color: offer.eligible ? G_VIB : GOLD,
            border: `1px solid ${offer.eligible ? G_VIB : GOLD}30`
          }}>
          {offer.eligibility}
        </span>
      </div>

      <p className="text-xs mb-4 leading-relaxed" style={{ color: "rgba(255,255,255,0.55)" }}>
        {offer.detail}
      </p>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="text-center p-2 rounded-lg" style={{ background: "rgba(255,255,255,0.04)" }}>
          <p className="text-[10px]" style={{ color: "rgba(255,255,255,0.35)" }}>Max Amount</p>
          <p className="text-sm font-mono font-bold" style={{ color: offer.color }}>
            KES {offer.max_amount.toLocaleString()}
          </p>
        </div>
        <div className="text-center p-2 rounded-lg" style={{ background: "rgba(255,255,255,0.04)" }}>
          <p className="text-[10px]" style={{ color: "rgba(255,255,255,0.35)" }}>Interest</p>
          <p className="text-sm font-mono font-bold text-white">{offer.interest_rate}</p>
        </div>
        <div className="text-center p-2 rounded-lg" style={{ background: "rgba(255,255,255,0.04)" }}>
          <p className="text-[10px]" style={{ color: "rgba(255,255,255,0.35)" }}>Tenor</p>
          <p className="text-sm font-mono font-bold text-white">{offer.tenor}</p>
        </div>
      </div>

      <div className="mb-4">
        <div className="flex justify-between text-xs mb-1">
          <span style={{ color: "rgba(255,255,255,0.35)" }}>Match Score</span>
          <span className="font-semibold font-mono" style={{ color: offer.color }}>{offer.match}%</span>
        </div>
        <div className="h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${offer.match}%` }}
            transition={{ duration: 0.9, ease: "easeOut", delay: 0.3 }}
            className="h-full rounded-full"
            style={{ background: offer.color }}
          />
        </div>
      </div>

      <div className="flex items-center gap-2 mb-3">
        <Info size={10} style={{ color: "rgba(255,255,255,0.3)" }} />
        <p className="text-[10px]" style={{ color: "rgba(255,255,255,0.3)" }}>
          Requires: {offer.requires.map((r: string) => r.replace("_", " ")).join(", ")}
        </p>
      </div>

      <motion.button
        onClick={handleApply}
        disabled={applied}
        whileHover={!applied ? { scale: 1.02 } : {}}
        whileTap={!applied ? { scale: 0.98 } : {}}
        className="w-full py-2.5 rounded-xl text-xs font-bold transition-all"
        style={{
          background: applied ? `${G_VIB}15` : `${offer.color}15`,
          color: applied ? G_VIB : offer.color,
          border: `1px solid ${applied ? G_VIB : offer.color}25`,
          cursor: applied ? "default" : "pointer",
        }}
      >
        {applied ? (
          <span className="flex items-center justify-center gap-1.5">
            <CheckCircle2 size={12} /> Application Submitted
          </span>
        ) : (
          <span className="flex items-center justify-center gap-1.5">
            <Zap size={12} /> Apply Now
          </span>
        )}
      </motion.button>
    </motion.div>
  );
}

// ── Action Item Card ──────────────────────────────────────────────────────────
function ActionItem({ title, description, severity, onAction }: {
  title: string; description: string; severity: "error" | "warning" | "info"; onAction?: () => void;
}) {
  const colors = {
    error: { bg: "#F8717115", border: "#F8717130", icon: R_LIGHT },
    warning: { bg: "#F4A26115", border: "#F4A26130", icon: GOLD },
    info: { bg: "#38BDF815", border: "#38BDF830", icon: SKY },
  };
  const c = colors[severity];

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      className="p-4 rounded-xl mb-3"
      style={{ background: c.bg, border: `1px solid ${c.border}` }}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle size={16} style={{ color: c.icon, flexShrink: 0, marginTop: 2 }} />
        <div className="flex-1">
          <p className="font-semibold text-sm" style={{ color: c.icon }}>{title}</p>
          <p className="text-xs mt-1 leading-relaxed" style={{ color: "rgba(255,255,255,0.6)" }}>{description}</p>
        </div>
        {onAction && (
          <motion.button
            onClick={onAction}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold shrink-0"
            style={{ background: c.icon, color: "#071410" }}
          >
            Fix
          </motion.button>
        )}
      </div>
    </motion.div>
  );
}

// ── Ambient Background ────────────────────────────────────────────────────────
function AmbientBg() {
  return (
    <>
      <div style={{
        position: "fixed", top: "-20%", left: "-10%", width: 700, height: 700,
        borderRadius: "50%", background: "radial-gradient(circle, rgba(11,110,79,0.18) 0%, transparent 65%)",
        pointerEvents: "none", zIndex: 0,
      }} />
      <div style={{
        position: "fixed", bottom: "-20%", right: "-10%", width: 600, height: 600,
        borderRadius: "50%", background: "radial-gradient(circle, rgba(124,58,237,0.12) 0%, transparent 65%)",
        pointerEvents: "none", zIndex: 0,
      }} />
    </>
  );
}

// ── Skeleton Loader ─────────────────────────────────────────────────────────
function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`rounded-xl animate-pulse ${className}`} style={{ background: "rgba(255,255,255,0.04)" }} />;
}

// ── MAIN COMPONENT ────────────────────────────────────────────────────────────
export default function FarmerSelfView({ farmerId }: { farmerId?: string }) {
  const [farmer, setFarmer] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [appliedOffers, setAppliedOffers] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!farmerId) {
      setError("No farmer ID provided");
      setLoading(false);
      return;
    }

    fetch(`${API_BASE}/api/farmers/${farmerId}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Failed to load profile (${res.status})`);
        return res.json();
      })
      .then((data) => {
        setFarmer(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to load profile");
        setLoading(false);
      });
  }, [farmerId]);

  const handleApply = (offer: any) => {
    setAppliedOffers((prev) => new Set(prev).add(`${offer.provider}-${offer.type}`));
    // TODO: POST to /api/offers/apply or similar
    console.log("Applied for:", offer);
  };

  if (loading) {
    return (
      <div style={{
        minHeight: "100vh", background: "linear-gradient(135deg, #071410 0%, #0B1F16 50%, #060d09 100%)",
        position: "relative", overflow: "hidden", fontFamily: "'Inter', sans-serif",
      }}>
        <AmbientBg />
        <div style={{ position: "relative", zIndex: 1, maxWidth: 640, margin: "0 auto", padding: "40px 20px" }}>
          <Skeleton className="h-32 mb-6" />
          <Skeleton className="h-48 mb-6" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (error || !farmer) {
    return (
      <div style={{
        minHeight: "100vh", background: "linear-gradient(135deg, #071410 0%, #0B1F16 50%, #060d09 100%)",
        display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16,
      }}>
        <AmbientBg />
        <div style={{ position: "relative", zIndex: 1, textAlign: "center" }}>
          <div style={{
            width: 56, height: 56, borderRadius: "50%", background: `${R_LIGHT}15`,
            border: `1px solid ${R_LIGHT}30`, display: "flex", alignItems: "center", justifyContent: "center",
            margin: "0 auto 16px",
          }}>
            <AlertTriangle size={24} style={{ color: R_LIGHT }} />
          </div>
          <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.2rem", letterSpacing: "0.04em" }}>
            Profile Not Found
          </p>
          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "1rem", marginTop: 8 }}>
            {error || "Could not load your profile. Please try again."}
          </p>
        </div>
      </div>
    );
  }

  const { color: statusColor, label: statusLabel, Icon: StatusIcon } = statusCfg(farmer.status);
  const verifiedCount = farmer.verifications?.filter((v: any) => v.status === "Verified").length ?? 0;
  const totalClaims = farmer.verifications?.length ?? 0;
  const hasConflicts = farmer.verifications?.some((v: any) => v.conflictsWithIds?.length > 0);
  const missingClaims = farmer.completenessReasons?.filter((r: any) => r.status === "missing") ?? [];
  const conflictClaims = farmer.completenessReasons?.filter((r: any) => r.status === "conflict") ?? [];

  return (
    <div style={{
      minHeight: "100vh",
      background: "linear-gradient(135deg, #071410 0%, #0B1F16 50%, #060d09 100%)",
      position: "relative", overflow: "hidden", fontFamily: "'Inter', sans-serif",
    }}>
      <AmbientBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 680, margin: "0 auto", padding: "28px 20px 80px" }}>

        {/* ── HEADER ─────────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          style={{ ...gl(0.06), padding: "24px 20px", marginBottom: 20 }}
        >
          <div className="flex items-start gap-4 mb-5">
            <Avatar name={farmer.name} size={56} color={statusColor} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <h1 style={{
                  fontFamily: "'Anton', sans-serif", color: "#fff",
                  fontSize: "1.3rem", letterSpacing: "0.03em", lineHeight: 1.2,
                }}>
                  {farmer.name}
                </h1>
                <StatusPill status={farmer.status} />
              </div>
              <p className="text-sm flex items-center gap-1.5 flex-wrap" style={{ color: "rgba(255,255,255,0.45)" }}>
                <MapPin size={12} />
                {farmer.location}
                {farmer.country && (
                  <span className="flex items-center gap-1">
                    <Globe size={11} /> {farmer.country}
                  </span>
                )}
              </p>
              <div className="flex flex-wrap gap-2 mt-2">
                {farmer.verified && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold"
                    style={{ background: `${G_VIB}15`, color: G_VIB, border: `1px solid ${G_VIB}30` }}>
                    <BadgeCheck size={10} /> ID Verified
                  </span>
                )}
                {farmer.consent_signed && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold"
                    style={{ background: `${SKY}15`, color: SKY, border: `1px solid ${SKY}30` }}>
                    <CheckCircle2 size={10} /> Consent Signed
                  </span>
                )}
                {hasConflicts && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold"
                    style={{ background: `${R_LIGHT}15`, color: R_LIGHT, border: `1px solid ${R_LIGHT}30` }}>
                    <AlertTriangle size={10} /> Has Conflicts
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Quick stats row */}
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center p-3 rounded-xl" style={{ background: "rgba(255,255,255,0.04)" }}>
              <p style={{ fontFamily: "'Anton', sans-serif", color: G_VIB, fontSize: "1.4rem", lineHeight: 1 }}>
                {farmer.completeness}%
              </p>
              <p className="text-[10px] mt-1" style={{ color: "rgba(255,255,255,0.35)" }}>Complete</p>
            </div>
            <div className="text-center p-3 rounded-xl" style={{ background: "rgba(255,255,255,0.04)" }}>
              <p style={{ fontFamily: "'Anton', sans-serif", color: riskColor(farmer.riskScore), fontSize: "1.4rem", lineHeight: 1 }}>
                {farmer.riskScore}
              </p>
              <p className="text-[10px] mt-1" style={{ color: "rgba(255,255,255,0.35)" }}>Risk Score</p>
            </div>
            <div className="text-center p-3 rounded-xl" style={{ background: "rgba(255,255,255,0.04)" }}>
              <p style={{ fontFamily: "'Anton', sans-serif", color: G_VIB, fontSize: "1.4rem", lineHeight: 1 }}>
                {verifiedCount}/{totalClaims}
              </p>
              <p className="text-[10px] mt-1" style={{ color: "rgba(255,255,255,0.35)" }}>Verified</p>
            </div>
          </div>
        </motion.div>

        {/* ── RISK SCORE ───────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.5 }}
          style={{ ...gl(0.06), padding: "20px 20px", marginBottom: 20 }}
        >
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={15} style={{ color: GOLD }} />
            <p style={{
              fontFamily: "'Anton', sans-serif", color: "#fff",
              fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase",
            }}>
              Risk Assessment
            </p>
          </div>
          <RiskRing score={farmer.riskScore} />
          {farmer.statusReason && (
            <div className="mt-4 p-3 rounded-xl" style={{
              background: `${farmer.statusReason.severity === "success" ? G_VIB :
                farmer.statusReason.severity === "warning" ? GOLD :
                  farmer.statusReason.severity === "error" ? R_LIGHT : SKY}12`,
              border: `1px solid ${farmer.statusReason.severity === "success" ? G_VIB :
                farmer.statusReason.severity === "warning" ? GOLD :
                  farmer.statusReason.severity === "error" ? R_LIGHT : SKY}30`,
            }}>
              <div className="flex items-start gap-2">
                <Info size={14} style={{ color: farmer.statusReason.severity === "success" ? G_VIB :
                  farmer.statusReason.severity === "warning" ? GOLD :
                    farmer.statusReason.severity === "error" ? R_LIGHT : SKY, flexShrink: 0, marginTop: 1 }} />
                <div>
                  <p className="font-semibold text-sm" style={{ color: farmer.statusReason.severity === "success" ? G_VIB :
                    farmer.statusReason.severity === "warning" ? GOLD :
                      farmer.statusReason.severity === "error" ? R_LIGHT : SKY }}>
                    {farmer.statusReason.title}
                  </p>
                  <p className="text-xs mt-0.5 leading-relaxed" style={{ color: "rgba(255,255,255,0.55)" }}>
                    {farmer.statusReason.description}
                  </p>
                </div>
              </div>
            </div>
          )}
        </motion.div>

        {/* ── ACTION ITEMS ──────────────────────────────────────────────────── */}
        {(missingClaims.length > 0 || conflictClaims.length > 0) && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15, duration: 0.5 }}
            className="mb-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <Zap size={15} style={{ color: R_LIGHT }} />
              <p style={{
                fontFamily: "'Anton', sans-serif", color: "#fff",
                fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase",
              }}>
                Action Required
              </p>
            </div>
            {conflictClaims.map((r: any, i: number) => (
              <ActionItem
                key={`conflict-${i}`}
                title={`${r.type}: Conflicting Data`}
                description={r.reason}
                severity="error"
              />
            ))}
            {missingClaims.map((r: any, i: number) => (
              <ActionItem
                key={`missing-${i}`}
                title={`${r.type}: Missing`}
                description={r.reason}
                severity="warning"
                onAction={() => {/* TODO: navigate to onboarding step */}}
              />
            ))}
          </motion.div>
        )}

        {/* ── VERIFICATIONS ─────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="mb-5"
        >
          <div className="flex items-center gap-2 mb-4">
            <Shield size={15} style={{ color: G_VIB }} />
            <p style={{
              fontFamily: "'Anton', sans-serif", color: "#fff",
              fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase",
            }}>
              Your Verifications
            </p>
          </div>
          <div className="space-y-3">
            {farmer.verifications?.map((v: any, i: number) => (
              <VerificationCard key={v.id || v.type} v={v} index={i} />
            ))}
          </div>
        </motion.div>

        {/* ── OFFERS ────────────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.5 }}
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Banknote size={15} style={{ color: GOLD }} />
              <p style={{
                fontFamily: "'Anton', sans-serif", color: "#fff",
                fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase",
              }}>
                Matching Offers
              </p>
            </div>
            <span className="text-[11px] px-2 py-0.5 rounded-full" style={{
              background: `${G_VIB}12`, color: G_VIB, border: `1px solid ${G_VIB}25`,
            }}>
              {farmer.offers?.length ?? 0} available
            </span>
          </div>

          {farmer.offers?.length > 0 ? (
            <div className="space-y-3">
              {farmer.offers.map((offer: any, i: number) => (
                <OfferCard
                  key={`${offer.provider}-${offer.type}`}
                  offer={offer}
                  index={i}
                  onApply={handleApply}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-10 rounded-xl" style={{ ...gl(0.04) }}>
              <Package size={32} style={{ color: "rgba(255,255,255,0.15)", margin: "0 auto 12px" }} />
              <p className="text-sm font-semibold text-white mb-1">No Offers Yet</p>
              <p className="text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
                Complete more verifications to unlock personalized loan and insurance offers.
              </p>
            </div>
          )}
        </motion.div>

        {/* ── FOOTER ────────────────────────────────────────────────────────── */}
        <div className="text-center mt-10">
          <p className="text-[10px]" style={{ color: "rgba(255,255,255,0.2)", fontFamily: "'Caveat', cursive" }}>
            Verified Data · Better Decisions · Stronger Farmers
          </p>
        </div>
      </div>
    </div>
  );
}
