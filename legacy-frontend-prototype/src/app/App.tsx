import { useState, useEffect } from "react";
import { fetchAllFarmers, searchFarmer, openVerificationStream } from "@/app/api/verifarm";
import { motion } from "motion/react";
import {
  LayoutDashboard, Users, BarChart3, Settings, LogOut,
  CheckCircle2, XCircle, Clock, Search,
  Bell, ArrowUpRight, ArrowDownRight, Shield,
  Leaf, CreditCard, Umbrella, Package, ThumbsUp,
  ThumbsDown, MessageSquare, MapPin, Sprout,
  TrendingUp, Download, Zap, UserCheck,
  Building2, Banknote, X, Menu, Landmark, User,
  ToggleLeft, ToggleRight, AlertTriangle, Globe, BadgeCheck,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { ImageWithFallback } from "@/app/components/figma/ImageWithFallback";
import verifarmLogo from "@/imports/ChatGPT_Image_Jun_24__2026__07_28_39_AM.png";
import heroPhoto from "@/imports/ChatGPT_Image_Jun_24__2026__10_45_34_AM.png";
import FarmerOnboarding from "@/pages/FarmerOnboarding";
import FarmerSelfView from "@/pages/FarmerSelfView";

// ── Brand ────────────────────────────────────────────────────────────────────
const G_VIB   = "#4ADE80";
const GOLD    = "#F4A261";
const PURPLE  = "#7C3AED";
const P_LIGHT = "#A78BFA";
const R_LIGHT = "#F87171";
const SKY     = "#38BDF8";

// ── Icon map: API returns icon names as strings ───────────────────────────────
const ICON_MAP: Record<string, React.ElementType> = {
  UserCheck,
  CreditCard,
  Leaf,
  Umbrella,
  Package,
  Shield,
  Banknote,
  Building2,
};

// ── Glassmorphism helpers ────────────────────────────────────────────────────
const gl = (alpha = 0.05, blur = 20): React.CSSProperties => ({
  background: `rgba(255,255,255,${alpha})`,
  backdropFilter: `blur(${blur}px)`,
  WebkitBackdropFilter: `blur(${blur}px)`,
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 16,
  boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
});

const glActive = (color: string): React.CSSProperties => ({
  ...gl(0.08),
  border: `1px solid ${color}40`,
  boxShadow: `0 8px 32px rgba(0,0,0,0.35), 0 0 0 1px ${color}20`,
});

const TICK  = { fill: "rgba(255,255,255,0.4)", fontSize: 11 };
const GRID  = "rgba(255,255,255,0.04)";
const TIP: React.CSSProperties = {
  background: "rgba(5,16,14,0.97)",
  backdropFilter: "blur(16px)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 10,
  color: "#fff",
  fontSize: 12,
};

// ── Motion variants ──────────────────────────────────────────────────────────
const PAGE = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
};
const CONT = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.06 } },
};
const ITEM = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.48, ease: "easeOut" } },
};
const FADE = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.4 } },
};

const approvalTrend = [
  { month: "Jan", approved: 42, rejected: 12, pending: 18 },
  { month: "Feb", approved: 55, rejected: 10, pending: 22 },
  { month: "Mar", approved: 48, rejected: 15, pending: 14 },
  { month: "Apr", approved: 63, rejected: 9,  pending: 20 },
  { month: "May", approved: 71, rejected: 8,  pending: 17 },
  { month: "Jun", approved: 68, rejected: 11, pending: 25 },
];

const cropDist = [
  { name: "Maize",   value: 38, color: G_VIB   },
  { name: "Rice",    value: 22, color: GOLD     },
  { name: "Wheat",   value: 18, color: P_LIGHT  },
  { name: "Sorghum", value: 12, color: SKY      },
  { name: "Other",   value: 10, color: "rgba(255,255,255,0.3)" },
];

const verifCoverage = [
  { category: "Identity",   verified: 92, unverified: 8  },
  { category: "Land",       verified: 74, unverified: 26 },
  { category: "Production", verified: 68, unverified: 32 },
  { category: "Credit",     verified: 41, unverified: 59 },
];

const portfolioTrend = [
  { month: "Jan", value: 3.2 }, { month: "Feb", value: 3.8 },
  { month: "Mar", value: 3.5 }, { month: "Apr", value: 4.1 },
  { month: "May", value: 4.6 }, { month: "Jun", value: 5.2 },
];

// ── Utilities ─────────────────────────────────────────────────────────────────
function statusCfg(s: string) {
  if (s === "approved") return { color: G_VIB,  label: "Approved", Icon: CheckCircle2 };
  if (s === "rejected") return { color: R_LIGHT, label: "Rejected", Icon: XCircle      };
  return                       { color: GOLD,    label: "Pending",  Icon: Clock        };
}
function vColor(s: string) { return s === "Verified" ? G_VIB : s === "Pending" ? GOLD : R_LIGHT; }
function riskColor(n: number) { return n >= 70 ? G_VIB : n >= 50 ? GOLD : R_LIGHT; }

// ── Shared components ─────────────────────────────────────────────────────────

function GCard({
  children, className = "", style = {}, hover = false, variants,
}: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  hover?: boolean;
  variants?: Record<string, unknown>;
}) {
  return (
    <motion.div
      className={`overflow-hidden ${className}`}
      style={{ ...gl(), ...style }}
      variants={variants}
      whileHover={hover ? { y: -3, boxShadow: "0 20px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.15)" } : undefined}
      transition={{ duration: 0.22 }}
    >
      {children}
    </motion.div>
  );
}

function Avatar({ name, size = 52, color = G_VIB }: { name: string; size?: number; color?: string }) {
  const initials = name.trim().split(/\s+/).map(w => w[0]?.toUpperCase() ?? "").slice(0, 2).join("");
  return (
    <div
      style={{
        width: size, height: size, borderRadius: "50%", flexShrink: 0,
        background: `${color}18`, border: `1.5px solid ${color}35`,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <span style={{ fontFamily: "'Anton', sans-serif", fontSize: size * 0.34, color, letterSpacing: "0.02em" }}>
        {initials}
      </span>
    </div>
  );
}

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

function ConfidenceBar({ value, color = G_VIB }: { value: number; color?: string }) {
  if (!value) return <span className="text-xs italic" style={{ color: "rgba(255,255,255,0.3)" }}>No data</span>;
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
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

function RiskRing({ score, factors }: { score: number; factors: any[] }) {
  const c = riskColor(score);
  const label = score >= 70 ? "Low Risk" : score >= 50 ? "Medium Risk" : "High Risk";
  const circumference = 2 * Math.PI * 28;
  const dash = (score / 100) * circumference;
  const hasConflict = factors.some(f => f.conflicted);

  return (
    <div>
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
          {hasConflict && (
            <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center"
              style={{ background: `${R_LIGHT}20`, border: `1px solid ${R_LIGHT}40` }}>
              <AlertTriangle size={10} style={{ color: R_LIGHT }} />
            </div>
          )}
        </div>
        <div>
          <p className="font-semibold text-sm" style={{ color: c }}>{label}</p>
          <p className="text-xs mt-1 leading-relaxed" style={{ color: "rgba(255,255,255,0.45)" }}>
            {hasConflict
              ? "Score suppressed by unresolved data conflicts. Resolve to unlock full rating."
              : "Composite score from verified identity, land records, production and cooperative standing."
            }
          </p>
        </div>
      </div>
      <div className="mt-5 space-y-3">
        {factors.map(({ label, score, positive, weight, conflicted }) => (
          <div key={label}>
            <div className="flex items-center justify-between text-xs mb-1">
              <div className="flex items-center gap-1.5">
                <span style={{ color: "rgba(255,255,255,0.5)" }}>{label}</span>
                <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.3)" }}>
                  {weight}%
                </span>
                {conflicted && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold"
                    style={{ background: `${R_LIGHT}18`, color: R_LIGHT, border: `1px solid ${R_LIGHT}30` }}>
                    <AlertTriangle size={8} /> conflict
                  </span>
                )}
              </div>
              <span className="font-mono font-semibold" style={{ color: conflicted ? R_LIGHT : (positive ? G_VIB : GOLD) }}>
                {score > 0 ? score : "—"}
              </span>
            </div>
            <div className="h-1 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
              {score > 0 && (
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${score}%` }}
                  transition={{ duration: 0.8, ease: "easeOut", delay: 0.15 }}
                  className="h-full rounded-full"
                  style={{ background: conflicted ? R_LIGHT : (positive ? G_VIB : GOLD) }}
                />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const { color, label, Icon } = statusCfg(status);
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold"
      style={{ background: `${color}18`, color, border: `1px solid ${color}30` }}>
      <Icon size={10} /> {label}
    </span>
  );
}

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`rounded-xl animate-pulse ${className}`} style={{ background: "rgba(255,255,255,0.04)" }} />;
}

function DecisionButtons({ onDecide }: { onDecide: (d: string) => void }) {
  return (
    <div className="flex flex-wrap gap-3">
      {[
        { d: "approved", label: "Approve",      Icon: ThumbsUp,      bg: G_VIB,   text: "#071410" },
        { d: "rejected", label: "Reject",       Icon: ThumbsDown,    bg: R_LIGHT, text: "#071410" },
        { d: "info",     label: "Request Info", Icon: MessageSquare, bg: "transparent", text: P_LIGHT, border: P_LIGHT },
      ].map(({ d, label, Icon, bg, text, border }) => (
        <motion.button
          key={d}
          onClick={() => onDecide(d)}
          whileHover={{ scale: 1.03, y: -1 }}
          whileTap={{ scale: 0.97 }}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all"
          style={{
            background: bg, color: text,
            border: border ? `1px solid ${border}` : "none",
            boxShadow: bg !== "transparent" ? `0 0 20px ${bg}30` : undefined,
          }}
        >
          <Icon size={14} /> {label}
        </motion.button>
      ))}
    </div>
  );
}

function OfferCard({ offer }: { offer: any }) {
  // Icon comes from API as a string — resolve to a real component
  const OfferIcon: React.ElementType = ICON_MAP[offer.Icon] ?? Package;
  const eligible = offer.status === "eligible";
  return (
    <motion.div
      variants={ITEM}
      whileHover={{ y: -2, boxShadow: `0 20px 60px rgba(0,0,0,0.5), 0 0 0 1px ${offer.color}30` }}
      transition={{ duration: 0.22 }}
      style={{ ...gl(0.06), padding: 20, cursor: "default" }}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div style={{ width: 38, height: 38, borderRadius: 10, background: `${offer.color}15`, border: `1px solid ${offer.color}30`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <OfferIcon size={17} style={{ color: offer.color }} />
          </div>
          <div>
            <p className="font-semibold text-sm text-white">{offer.type}</p>
            <p className="text-xs" style={{ color: "rgba(255,255,255,0.45)" }}>{offer.provider}</p>
          </div>
        </div>
        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{ background: eligible ? `${G_VIB}15` : `${GOLD}15`, color: eligible ? G_VIB : GOLD }}>
          {eligible ? "Eligible" : "Partial"}
        </span>
      </div>
      <p className="text-xs mb-3" style={{ color: "rgba(255,255,255,0.55)" }}>{offer.detail}</p>
      <div className="mb-3">
        <div className="flex justify-between text-xs mb-1">
          <span style={{ color: "rgba(255,255,255,0.35)" }}>Match score</span>
          <span className="font-semibold font-mono" style={{ color: offer.color }}>{offer.match}%</span>
        </div>
        <div className="h-1 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${offer.match}%` }}
            transition={{ duration: 0.9, ease: "easeOut", delay: 0.2 }}
            className="h-full rounded-full"
            style={{ background: offer.color }}
          />
        </div>
      </div>
      <motion.button
        whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
        className="w-full py-2 rounded-lg text-xs font-semibold transition-all"
        style={{ background: `${offer.color}15`, color: offer.color, border: `1px solid ${offer.color}25` }}
      >
        View Details
      </motion.button>
    </motion.div>
  );
}

function FarmerListItem({ farmer, selected, onClick }: { farmer: any; selected: boolean; onClick: () => void }) {
  const rc = riskColor(farmer.riskScore);
  return (
    <motion.button
      onClick={onClick}
      whileHover={{ x: 3 }}
      transition={{ duration: 0.18 }}
      className="w-full text-left p-4 rounded-xl transition-all"
      style={{
        background: selected ? `${G_VIB}12` : "rgba(255,255,255,0.03)",
        border: selected ? `1px solid ${G_VIB}35` : "1px solid rgba(255,255,255,0.06)",
        marginBottom: 6,
      }}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2.5">
          <Avatar name={farmer.name} size={34} color={statusCfg(farmer.status).color} />
          <div>
            <p className="text-sm font-semibold text-white leading-tight">{farmer.name}</p>
            <p className="text-[11px] flex items-center gap-1 mt-0.5" style={{ color: "rgba(255,255,255,0.4)" }}>
              <MapPin size={9} /> {farmer.location}
              {farmer.country ? `, ${farmer.country}` : ""}
            </p>
          </div>
        </div>
        <StatusPill status={farmer.status} />
      </div>
      <div className="flex items-center justify-between mt-2.5">
        <div className="flex items-center gap-1.5">
          <Leaf size={10} style={{ color: G_VIB }} />
          <span className="text-[11px]" style={{ color: "rgba(255,255,255,0.45)" }}>{farmer.crop} · {farmer.farmSize}</span>
        </div>
        <span className="font-mono text-xs font-bold" style={{ color: rc }}>{farmer.riskScore}</span>
      </div>
      <div className="mt-2">
        <div className="h-0.5 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
          <div className="h-full rounded-full transition-all" style={{ width: `${farmer.completeness}%`, background: G_VIB }} />
        </div>
        <p className="text-[10px] mt-0.5 text-right" style={{ color: "rgba(255,255,255,0.3)" }}>{farmer.completeness}% complete</p>
      </div>
    </motion.button>
  );
}

function TrustGraph({ farmer }: { farmer: any }) {
  const nodes = [
    { label: farmer.name.split(" ")[0], sub: "Farmer",         color: G_VIB,   Icon: User      },
    { label: "Co-op",                   sub: "Cooperative",    color: P_LIGHT, Icon: Building2 },
    { label: "Off-taker",               sub: "Market buyer",   color: GOLD,    Icon: Package   },
    { label: "Lender",                  sub: "Financial inst.", color: SKY,    Icon: Landmark  },
  ];
  return (
    <div className="flex items-center justify-between gap-1 overflow-x-auto py-3">
      {nodes.map((n, i) => (
        <div key={i} className="flex items-center gap-1 shrink-0">
          <motion.div
            initial={{ scale: 0.7, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: i * 0.12, duration: 0.4, ease: "easeOut" }}
            className="flex flex-col items-center text-center"
          >
            <div style={{ width: 44, height: 44, borderRadius: "50%", background: `${n.color}15`, border: `1.5px solid ${n.color}40`, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <n.Icon size={17} style={{ color: n.color }} />
            </div>
            <p className="text-[11px] font-semibold mt-1.5 leading-tight" style={{ color: n.color, maxWidth: 58 }}>{n.label}</p>
            <p className="text-[9px]" style={{ color: "rgba(255,255,255,0.3)" }}>{n.sub}</p>
          </motion.div>
          {i < nodes.length - 1 && (
            <motion.div
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ delay: i * 0.12 + 0.2, duration: 0.35 }}
              style={{ originX: 0, width: 28, height: 1, background: `linear-gradient(90deg, ${nodes[i].color}60, ${nodes[i+1].color}60)`, flexShrink: 0, margin: "0 2px", marginBottom: 20 }}
            />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Ambient background glows ──────────────────────────────────────────────────
function AmbientBg() {
  return (
    <>
      <div style={{ position: "fixed", top: "-20%", left: "-10%", width: 700, height: 700, borderRadius: "50%", background: "radial-gradient(circle, rgba(11,110,79,0.22) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />
      <div style={{ position: "fixed", bottom: "-20%", right: "-10%", width: 600, height: 600, borderRadius: "50%", background: "radial-gradient(circle, rgba(124,58,237,0.16) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />
      <div style={{ position: "fixed", top: "45%", left: "55%", width: 400, height: 400, borderRadius: "50%", background: "radial-gradient(circle, rgba(244,162,97,0.08) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />
    </>
  );
}

// ── Section header helper ─────────────────────────────────────────────────────
function SectionHead({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <h1 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.75rem", lineHeight: 1.1, letterSpacing: "0.04em", textTransform: "uppercase" }}>
        {title}
      </h1>
      {sub && (
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.5)", fontSize: "1.2rem", marginTop: 4 }}>
          {sub}
        </p>
      )}
    </div>
  );
}

// ── LOGIN ─────────────────────────────────────────────────────────────────────
function LoginPage({ onLogin }: { onLogin: (role: string) => void }) {
  const [email, setEmail]       = useState("grace.mwangi@kcb.co.ke");
  const [password, setPassword] = useState("••••••••");

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "11px 14px", borderRadius: 10,
    background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.12)",
    color: "#fff", fontSize: 14, outline: "none", fontFamily: "'Inter', sans-serif",
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.6 }}
      style={{ minHeight: "100vh", display: "grid", gridTemplateColumns: "repeat(2,1fr)" }}
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
                { val: "94%",     sub: "Data accuracy"    },
                { val: "3.2×",    sub: "Faster decisions" },
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
              <input value={email} onChange={e => setEmail(e.target.value)} style={inputStyle} />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "rgba(255,255,255,0.55)", marginBottom: 6, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                Password
              </label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} style={inputStyle} />
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
  );
}

// ── DASHBOARD OVERVIEW ────────────────────────────────────────────────────────
function DashboardOverview({ onViewFarmer, farmers }: { onViewFarmer: (id: string) => void; farmers: any[] }) {
  const stats = [
    { label: "Total Farmers",  value: "1,284", note: "+48 this month",      up: true,  color: G_VIB,   Icon: Users        },
    { label: "Approved",       value: "847",   note: "65.9% approval rate", up: true,  color: G_VIB,   Icon: CheckCircle2 },
    { label: "Rejected",       value: "191",   note: "14.9% of total",      up: false, color: R_LIGHT,  Icon: XCircle      },
    { label: "Pending Review", value: "246",   note: "Avg 1.8 days wait",   up: null,  color: GOLD,    Icon: Clock        },
  ];

  return (
    <motion.div variants={PAGE} initial="hidden" animate="show" className="p-6 md:p-8 space-y-6 pb-12">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.75rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>
            Dashboard
          </h1>
          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "1.15rem", marginTop: 2 }}>
            Welcome back, Grace Mwangi · KCB Credit Division
          </p>
        </div>
        <div className="flex gap-2">
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-medium"
            style={{ ...gl(0.05), color: "rgba(255,255,255,0.6)" }}>
            <Download size={13} /> Export
          </motion.button>
          <motion.button whileHover={{ scale: 1.03, boxShadow: `0 0 20px ${G_VIB}35` }} whileTap={{ scale: 0.97 }}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-semibold"
            style={{ background: G_VIB, color: "#071410" }}>
            <Zap size={13} /> New Review
          </motion.button>
        </div>
      </div>

      {/* Stat cards */}
      <motion.div variants={CONT} initial="hidden" animate="show" className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map(({ label, value, note, up, color, Icon }) => (
          <motion.div key={label} variants={ITEM} whileHover={{ y: -3, boxShadow: `0 20px 60px rgba(0,0,0,0.5), 0 0 0 1px ${color}25` }} transition={{ duration: 0.2 }}
            style={{ ...gl(0.05), padding: 20 }}>
            <div className="flex items-start justify-between mb-3">
              <div style={{ width: 36, height: 36, borderRadius: 10, background: `${color}15`, border: `1px solid ${color}25`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Icon size={16} style={{ color }} />
              </div>
              {up !== null && (
                <span className="flex items-center text-xs" style={{ color: up ? G_VIB : R_LIGHT }}>
                  {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                </span>
              )}
            </div>
            <p style={{ fontFamily: "'Anton', sans-serif", color, fontSize: "1.7rem", lineHeight: 1 }}>{value}</p>
            <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "0.9rem", marginTop: 2 }}>{label}</p>
            <p className="text-xs mt-1.5" style={{ color: "rgba(255,255,255,0.3)" }}>{note}</p>
          </motion.div>
        ))}
      </motion.div>

      {/* Charts */}
      <div className="grid md:grid-cols-3 gap-5">
        <GCard className="p-5 md:col-span-2">
          <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.95rem", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 2 }}>
            Loan Approval Trends
          </p>
          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "1rem", marginBottom: 20 }}>
            Monthly breakdown — approved, pending, rejected
          </p>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={approvalTrend} barGap={3}>
              <XAxis dataKey="month" tick={TICK} axisLine={false} tickLine={false} />
              <YAxis tick={TICK} axisLine={false} tickLine={false} />
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <Tooltip contentStyle={TIP} />
              <Bar dataKey="approved" fill={G_VIB}  radius={[4,4,0,0]} name="Approved" />
              <Bar dataKey="pending"  fill={GOLD}   radius={[4,4,0,0]} name="Pending"  />
              <Bar dataKey="rejected" fill={R_LIGHT} radius={[4,4,0,0]} name="Rejected" />
            </BarChart>
          </ResponsiveContainer>
        </GCard>

        <GCard className="p-5">
          <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.95rem", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 2 }}>
            Crop Mix
          </p>
          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "1rem", marginBottom: 16 }}>
            Portfolio by crop type
          </p>
          <ResponsiveContainer width="100%" height={150}>
            <PieChart>
              <Pie data={cropDist} dataKey="value" cx="50%" cy="50%" outerRadius={60} innerRadius={38}>
                {cropDist.map((e, i) => <Cell key={i} fill={e.color} />)}
              </Pie>
              <Tooltip contentStyle={TIP} />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-2 mt-2">
            {cropDist.map(({ name, value, color }) => (
              <div key={name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5">
                  <div style={{ width: 7, height: 7, borderRadius: "50%", background: color }} />
                  <span style={{ color: "rgba(255,255,255,0.55)" }}>{name}</span>
                </div>
                <span className="font-mono font-semibold text-white">{value}%</span>
              </div>
            ))}
          </div>
        </GCard>
      </div>

      {/* Verification coverage */}
      <GCard className="p-5">
        <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.95rem", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 2 }}>
          Verification Coverage
        </p>
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "1rem", marginBottom: 20 }}>
          Percentage of profiles with each data type confirmed
        </p>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={verifCoverage} layout="vertical" barGap={2}>
            <XAxis type="number" tick={TICK} axisLine={false} tickLine={false} unit="%" />
            <YAxis type="category" dataKey="category" tick={{ ...TICK, fill: "rgba(255,255,255,0.55)" }} axisLine={false} tickLine={false} width={78} />
            <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
            <Tooltip contentStyle={TIP} />
            <Bar dataKey="verified"   fill={G_VIB}                   radius={[0,4,4,0]} name="Verified %"   stackId="a" />
            <Bar dataKey="unverified" fill="rgba(255,255,255,0.06)"  radius={[0,4,4,0]} name="Unverified %" stackId="a" />
          </BarChart>
        </ResponsiveContainer>
      </GCard>

      {/* Pending queue */}
      <GCard className="p-5">
        <div className="flex items-center justify-between mb-5">
          <div>
            <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.95rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>Pending Reviews</p>
            <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "1rem" }}>
              {farmers.filter(f => f.status === "pending").length} farmers awaiting decision
            </p>
          </div>
        </div>
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          {farmers.filter(f => f.status === "pending").map((f, i) => (
            <motion.div
              key={f.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.1, duration: 0.4 }}
              className="flex items-center justify-between py-4"
              style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}
            >
              <div className="flex items-center gap-3">
                <Avatar name={f.name} size={36} color={G_VIB} />
                <div>
                  <p className="text-sm font-semibold text-white">{f.name}</p>
                  <p className="text-xs flex items-center gap-1 mt-0.5" style={{ color: "rgba(255,255,255,0.4)" }}>
                    <MapPin size={10} /> {f.location}{f.country ? `, ${f.country}` : ""} · {f.crop} · {f.farmSize}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right hidden sm:block">
                  <p className="text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>Complete</p>
                  <p className="text-sm font-mono font-bold" style={{ color: G_VIB }}>{f.completeness}%</p>
                </div>
                <motion.button
                  onClick={() => onViewFarmer(f.id)}
                  whileHover={{ scale: 1.04, boxShadow: `0 0 16px ${G_VIB}30` }}
                  whileTap={{ scale: 0.97 }}
                  className="px-4 py-1.5 rounded-lg text-xs font-semibold"
                  style={{ background: G_VIB, color: "#071410" }}
                >
                  Review
                </motion.button>
              </div>
            </motion.div>
          ))}
        </div>
      </GCard>
    </motion.div>
  );
}

// ── STATUS REASON BANNER ──────────────────────────────────────────────────────
function StatusReasonBanner({ reason }: { reason: any }) {
  if (!reason) return null;
  const severityColors: Record<string, any> = {
    success: { bg: "#4ADE8015", border: "#4ADE8030", icon: G_VIB,   text: G_VIB   },
    warning: { bg: "#F4A26115", border: "#F4A26130", icon: GOLD,    text: GOLD    },
    error:   { bg: "#F8717115", border: "#F8717130", icon: R_LIGHT, text: R_LIGHT },
    info:    { bg: "#38BDF815", border: "#38BDF830", icon: SKY,     text: SKY     },
  };
  const c = severityColors[reason.severity] || severityColors.info;
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="p-4 rounded-xl mb-4"
      style={{ background: c.bg, border: `1px solid ${c.border}` }}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} style={{ color: c.icon, flexShrink: 0, marginTop: 2 }} />
        <div>
          <p className="font-semibold text-sm" style={{ color: c.text }}>{reason.title}</p>
          <p className="text-xs mt-1 leading-relaxed" style={{ color: "rgba(255,255,255,0.6)" }}>
            {reason.description}
          </p>
        </div>
      </div>
    </motion.div>
  );
}

function ConflictBadge({ count }: { count: number }) {
  if (!count) return null;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold"
      style={{ background: `${R_LIGHT}18`, color: R_LIGHT, border: `1px solid ${R_LIGHT}30` }}>
      <AlertTriangle size={9} /> {count} conflict{count > 1 ? "s" : ""}
    </span>
  );
}

function CompletenessReasons({ reasons }: { reasons: any[] }) {
  if (!reasons?.length) return null;
  const statusConfig: Record<string, { color: string; label: string }> = {
    verified: { color: G_VIB,   label: "Verified"  },
    pending:  { color: GOLD,    label: "Pending"   },
    missing:  { color: R_LIGHT, label: "Missing"   },
    conflict: { color: R_LIGHT, label: "Conflict"  },
  };
  return (
    <GCard className="p-5 mb-4">
      <div className="flex items-center gap-2 mb-4">
        <Shield size={15} style={{ color: P_LIGHT }} />
        <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase" }}>
          Data Completeness Breakdown
        </p>
      </div>
      <div className="space-y-3">
        {reasons.map((r, i) => {
          const cfg = statusConfig[r.status] || statusConfig.pending;
          return (
            <motion.div
              key={r.type}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.1, duration: 0.3 }}
              style={{ ...gl(0.04), padding: "14px 16px", border: `1px solid ${cfg.color}20` }}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  {r.status === "verified" ? <CheckCircle2 size={13} style={{ color: cfg.color }} /> :
                   r.status === "conflict"  ? <AlertTriangle size={13} style={{ color: cfg.color }} /> :
                   <Clock size={13} style={{ color: cfg.color }} />}
                  <span className="font-semibold text-sm text-white">{r.type}</span>
                </div>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                  style={{ background: `${cfg.color}15`, color: cfg.color, border: `1px solid ${cfg.color}25` }}>
                  {cfg.label}
                </span>
              </div>
              <p className="text-xs mb-2" style={{ color: "rgba(255,255,255,0.55)" }}>
                {r.reason}
              </p>
              {r.action && (
                <div className="flex items-center gap-1.5 text-[11px] font-medium"
                  style={{ color: P_LIGHT }}>
                  <Zap size={10} /> {r.action}
                </div>
              )}
              {r.conflicts && (
                <div className="mt-2 space-y-1.5">
                  {r.conflicts.map((conf: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between text-[11px] p-2 rounded-lg"
                      style={{ background: "rgba(255,255,255,0.03)" }}>
                      <span style={{ color: "rgba(255,255,255,0.6)" }}>{conf.source}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-mono" style={{ color: "rgba(255,255,255,0.4)" }}>{conf.value}</span>
                        <span className="font-mono font-semibold" style={{ color: conf.confidence >= 0.7 ? G_VIB : conf.confidence >= 0.4 ? GOLD : R_LIGHT }}>
                          {Math.round(conf.confidence * 100)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          );
        })}
      </div>
    </GCard>
  );
}

// ── FARMER PROFILE ────────────────────────────────────────────────────────────
function FarmerProfile({ farmerId, onBack, farmers }: { farmerId: any; onBack: () => void; farmers: any[] }) {
  // ── CRASH FIX: guard against empty/loading farmers array ──────────────────
  const farmer = Array.isArray(farmers) && farmers.length > 0
    ? (farmers.find(f => f.id === farmerId) ?? farmers[0])
    : null;

  if (!farmer) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300, flexDirection: "column", gap: 12 }}>
        <div className="animate-pulse" style={{ width: 48, height: 48, borderRadius: "50%", background: `${G_VIB}20`, border: `1px solid ${G_VIB}30` }} />
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "1.1rem" }}>Loading farmer profile…</p>
      </div>
    );
  }

  const [decision, setDecision] = useState<string | null>(farmer.status !== "pending" ? farmer.status : null);
  const verifiedCount = farmer.verifications?.filter((v: any) => v.status === "Verified").length ?? 0;
  const totalClaims   = farmer.verifications?.length ?? 0;

  return (
    <motion.div variants={PAGE} initial="hidden" animate="show" className="p-5 md:p-8 space-y-5 pb-12">
      <motion.button
        onClick={onBack}
        whileHover={{ x: -3 }}
        transition={{ duration: 0.18 }}
        className="flex items-center gap-1.5 text-sm font-medium"
        style={{ color: G_VIB, background: "none", border: "none", cursor: "pointer" }}
      >
        ← Back to farmers
      </motion.button>

      {/* Status Reason Banner */}
      {farmer.statusReason && <StatusReasonBanner reason={farmer.statusReason} />}

      {/* Decision banner */}
      {decision && decision !== "info" && (
        <motion.div
          initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
          className="flex items-center justify-between p-4 rounded-xl"
          style={{ background: `${decision === "approved" ? G_VIB : R_LIGHT}12`, border: `1px solid ${decision === "approved" ? G_VIB : R_LIGHT}30` }}
        >
          <div className="flex items-center gap-3">
            {decision === "approved" ? <CheckCircle2 size={18} style={{ color: G_VIB }} /> : <XCircle size={18} style={{ color: R_LIGHT }} />}
            <div>
              <p className="font-semibold text-sm" style={{ color: decision === "approved" ? G_VIB : R_LIGHT }}>
                Application {decision === "approved" ? "Approved" : "Rejected"}
              </p>
              <p className="text-xs mt-0.5" style={{ color: "rgba(255,255,255,0.4)" }}>
                {decision === "approved" ? "Forwarded to underwriting. KES 120,000 loan processing." : "Farmer notified. Missing credit history flagged."}
              </p>
            </div>
          </div>
          <button onClick={() => setDecision(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "rgba(255,255,255,0.4)" }}>
            <X size={16} />
          </button>
        </motion.div>
      )}

      {/* Overview card */}
      <GCard className="p-6">
        <div className="flex items-start justify-between flex-wrap gap-4 mb-5">
          <div className="flex items-start gap-4">
            <Avatar name={farmer.name} size={56} color={statusCfg(farmer.status).color} />
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h2 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.35rem", letterSpacing: "0.03em" }}>{farmer.name}</h2>
                <StatusPill status={farmer.status} />
                {/* ── NEW: verified + consent badges ── */}
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
              </div>
              <p className="text-sm flex items-center gap-1 mt-1" style={{ color: "rgba(255,255,255,0.45)" }}>
                <MapPin size={12} /> {farmer.location}
                {/* ── NEW: country ── */}
                {farmer.country && (
                  <span className="flex items-center gap-1 ml-1">
                    <Globe size={11} /> {farmer.country}
                  </span>
                )}
              </p>
              <div className="flex flex-wrap gap-3 mt-2">
                {[
                  { v: farmer.crop,        Icon: Leaf      },
                  { v: farmer.farmSize,    Icon: Sprout    },
                  { v: farmer.cooperative, Icon: Building2 },
                ].map(({ v, Icon }) => v ? (
                  <span key={v} className="flex items-center gap-1 text-xs" style={{ color: "rgba(255,255,255,0.45)" }}>
                    <Icon size={11} style={{ color: G_VIB }} /> {v}
                  </span>
                ) : null)}
              </div>
            </div>
          </div>
          {/* Completeness ring */}
          <div className="text-center">
            <div className="relative w-16 h-16">
              <svg width="64" height="64" className="-rotate-90">
                <circle cx="32" cy="32" r="24" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4" />
                <motion.circle cx="32" cy="32" r="24" fill="none" stroke={G_VIB} strokeWidth="4" strokeLinecap="round"
                  strokeDasharray={2 * Math.PI * 24}
                  initial={{ strokeDashoffset: 2 * Math.PI * 24 }}
                  animate={{ strokeDashoffset: 2 * Math.PI * 24 * (1 - farmer.completeness / 100) }}
                  transition={{ duration: 1, ease: "easeOut" }}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="font-mono font-bold text-base leading-none text-white">{farmer.completeness}</span>
                <span style={{ fontSize: 8, color: G_VIB }}>%</span>
              </div>
            </div>
            <p className="text-[10px] mt-1" style={{ color: "rgba(255,255,255,0.35)" }}>Complete</p>
          </div>
        </div>

        {/* ── EXPANDED DETAILS GRID (now shows all key fields) ── */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4 pt-4" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          {[
            { label: "Phone",        value: farmer.phone },
            { label: "Risk Score",   value: `${farmer.riskScore}/100`, color: riskColor(farmer.riskScore) },
            { label: "Verifications",value: `${verifiedCount} / ${totalClaims} verified` },
            { label: "Farm Size",    value: farmer.farmSize },
            { label: "Country",      value: farmer.country },
            { label: "Cooperative",  value: farmer.cooperative },
            { label: "Farmer ID",    value: farmer.id },
            {
              label: "GPS Coords",
              value: farmer.latitude && farmer.longitude
                ? `${farmer.latitude.toFixed(4)}, ${farmer.longitude.toFixed(4)}`
                : null,
            },
          ].filter(item => item.value).map(({ label, value, color }: any) => (
            <div key={label}>
              <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.35)", fontSize: "0.85rem" }}>{label}</p>
              <p className="text-sm font-semibold" style={{ color: color || "#fff" }}>{value}</p>
            </div>
          ))}
        </div>
      </GCard>

      <div className="grid md:grid-cols-5 gap-5">
        {/* Left col */}
        <div className="md:col-span-3 space-y-5">
          {/* Completeness Reasons */}
          {farmer.completenessReasons && <CompletenessReasons reasons={farmer.completenessReasons} />}

          {/* Verifications */}
          <GCard className="p-5">
            <div className="flex items-center gap-2 mb-4">
              <Shield size={15} style={{ color: G_VIB }} />
              <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                Verification Claims
              </p>
            </div>
            <motion.div variants={CONT} initial="hidden" animate="show" className="space-y-3">
              {farmer.verifications?.map((v: any) => (
                <motion.div key={v.id || v.type} variants={ITEM}
                  style={{ ...gl(0.04), border: `1px solid ${v.conflictsWithIds?.length ? R_LIGHT : vColor(v.status)}25`, padding: "14px 16px" }}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2.5">
                      <Shield size={14} style={{ color: v.conflictsWithIds?.length ? R_LIGHT : vColor(v.status) }} />
                      <p className="font-semibold text-sm text-white">{v.type}</p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {v.conflictsWithIds?.length > 0 && <ConflictBadge count={v.conflictsWithIds.length} />}
                      <VerifBadge status={v.status} />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.35)", fontSize: "0.8rem" }}>Source</p>
                      <p className="text-xs font-medium text-white mt-0.5">{v.source}</p>
                    </div>
                    <div>
                      <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.35)", fontSize: "0.8rem", marginBottom: 4 }}>Confidence</p>
                      <ConfidenceBar value={v.confidence} color={v.conflictsWithIds?.length ? R_LIGHT : vColor(v.status)} />
                    </div>
                  </div>

                  {/* ── NEW: Value, Method, Date ── */}
                  <div className="mt-3 pt-3 grid grid-cols-1 gap-2" style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
                    {v.value && (
                      <div>
                        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.35)", fontSize: "0.8rem" }}>Value</p>
                        <p className="text-xs font-mono text-white mt-0.5">{v.value}</p>
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-3 mt-1">
                      {v.method && (
                        <div>
                          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.35)", fontSize: "0.8rem" }}>Method</p>
                          <p className="text-xs font-mono text-white mt-0.5">{v.method.replace(/_/g, " ")}</p>
                        </div>
                      )}
                      {v.date && (
                        <div>
                          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.35)", fontSize: "0.8rem" }}>Date</p>
                          <p className="text-xs font-mono text-white mt-0.5">{v.date}</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {v.conflictsWithIds?.length > 0 && (
                    <div className="mt-2 p-2 rounded-lg" style={{ background: `${R_LIGHT}08`, border: `1px solid ${R_LIGHT}20` }}>
                      <p className="text-[10px] font-medium" style={{ color: R_LIGHT }}>
                        <AlertTriangle size={9} className="inline mr-1" />
                        Conflicts with {v.conflictsWithIds.length} other claim{v.conflictsWithIds.length > 1 ? "s" : ""}
                      </p>
                    </div>
                  )}
                </motion.div>
              ))}
            </motion.div>
          </GCard>

          {/* Trust network */}
          <GCard className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <Zap size={15} style={{ color: P_LIGHT }} />
              <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                Trust Network
              </p>
            </div>
            <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.35)", fontSize: "0.95rem", marginBottom: 12 }}>
              Data linkages across the verification chain
            </p>
            <TrustGraph farmer={farmer} />
          </GCard>

          {/* Decision */}
          <GCard className="p-5">
            <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 4 }}>
              Credit Decision
            </p>
            <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "0.95rem", marginBottom: 16 }}>
              Review the profile and make a final determination
            </p>
            <DecisionButtons onDecide={setDecision} />
          </GCard>
        </div>

        {/* Right col */}
        <div className="md:col-span-2 space-y-5">
          {/* Risk score */}
          <GCard className="p-5">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp size={15} style={{ color: GOLD }} />
              <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                Risk Score
              </p>
            </div>
            <RiskRing score={farmer.riskScore} factors={farmer.riskFactors || []} />
          </GCard>

          {/* Offers */}
          <div>
            <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 12 }}>
              Matching Offers
            </p>
            <motion.div variants={CONT} initial="hidden" animate="show" className="space-y-3">
              {farmer.offers?.length > 0 ? (
                farmer.offers.map((offer: any, i: number) => <OfferCard key={i} offer={offer} />)
              ) : (
                <div className="p-4 rounded-xl text-center" style={{ ...gl(0.04), color: "rgba(255,255,255,0.3)" }}>
                  <p className="text-sm">No offers available yet</p>
                  <p className="text-xs mt-1">Complete more verifications to unlock offers</p>
                </div>
              )}
            </motion.div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ── FARMERS LIST ──────────────────────────────────────────────────────────────
function FarmersList({ onViewFarmer, farmers }: { onViewFarmer: (id: string) => void; farmers: any[] }) {
  const [search, setSearch]     = useState("");
  const [sort, setSort]         = useState("riskScore");
  const [filter, setFilter]     = useState("all");
  const [selected, setSelected] = useState<any>(null);

  const filtered = (farmers ?? [])
    .filter(f =>
      (filter === "all" || f.status === filter) &&
      (f.name.toLowerCase().includes(search.toLowerCase()) ||
       f.location.toLowerCase().includes(search.toLowerCase()) ||
       f.crop.toLowerCase().includes(search.toLowerCase()))
    )
    .sort((a, b) =>
      sort === "riskScore"    ? b.riskScore - a.riskScore :
      sort === "completeness" ? b.completeness - a.completeness :
      a.name.localeCompare(b.name)
    );

  const farmer = selected !== null ? (farmers ?? []).find(f => f.id === selected) ?? null : null;

  return (
    <div className="flex" style={{ minHeight: "calc(100vh - 60px)" }}>
      {/* List */}
      <div
        className={`${selected ? "hidden md:flex" : "flex"} flex-col shrink-0 md:w-72`}
        style={{ borderRight: "1px solid rgba(255,255,255,0.06)", width: "100%" }}
      >
        <div className="p-4" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
          <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 12 }}>
            All Farmers
          </p>

          <div className="relative mb-3">
            <Search size={13} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "rgba(255,255,255,0.3)" }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Name, crop, location…"
              style={{ width: "100%", paddingLeft: 34, paddingRight: 12, paddingTop: 8, paddingBottom: 8, borderRadius: 10, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", color: "#fff", fontSize: 12, outline: "none", boxSizing: "border-box" }}
            />
          </div>

          <div className="flex gap-1.5 flex-wrap mb-2.5">
            {["all","pending","approved","rejected"].map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold capitalize transition-all"
                style={{ background: filter === f ? G_VIB : "rgba(255,255,255,0.06)", color: filter === f ? "#071410" : "rgba(255,255,255,0.45)", border: "none", cursor: "pointer" }}>
                {f}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <span style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Sort:</span>
            {[
              { val: "riskScore",    label: "Risk"     },
              { val: "completeness", label: "Complete" },
              { val: "name",         label: "Name"     },
            ].map(({ val, label }) => (
              <button key={val} onClick={() => setSort(val)}
                style={{ background: "none", border: "none", cursor: "pointer", fontSize: 11, fontWeight: sort === val ? 700 : 400, color: sort === val ? G_VIB : "rgba(255,255,255,0.3)" }}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {filtered.map(f => (
            <FarmerListItem key={f.id} farmer={f} selected={selected === f.id}
              onClick={() => setSelected(f.id)} />
          ))}
          {!filtered.length && (
            <div className="text-center py-12" style={{ color: "rgba(255,255,255,0.3)", fontSize: 14, fontFamily: "'Caveat', cursive" }}>
              No farmers match your filters
            </div>
          )}
        </div>
      </div>

      {/* Detail */}
      {farmer ? (
        <div className="flex-1 overflow-y-auto">
          <FarmerProfile farmerId={farmer.id} farmers={farmers} onBack={() => setSelected(null)} />
        </div>
      ) : (
        <div className="flex-1 hidden md:flex items-center justify-center text-center p-10">
          <motion.div initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.45 }}>
            <div style={{ width: 64, height: 64, borderRadius: 20, background: `${G_VIB}12`, border: `1px solid ${G_VIB}25`, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
              <Users size={26} style={{ color: G_VIB }} />
            </div>
            <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>
              Select a Farmer
            </p>
            <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.35)", fontSize: "1rem", marginTop: 6 }}>
              Choose from the list to view their full profile
            </p>
          </motion.div>
        </div>
      )}
    </div>
  );
}

// ── ANALYTICS ─────────────────────────────────────────────────────────────────
function AnalyticsPage({ farmers }: { farmers: any[] }) {
  return (
    <motion.div variants={PAGE} initial="hidden" animate="show" className="p-6 md:p-8 space-y-6 pb-12">
      <SectionHead
        title="Cooperative Analytics"
        sub="Portfolio-level insights across all cooperatives and regions"
      />

      <motion.div variants={CONT} initial="hidden" animate="show" className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Cooperatives",          value: "34",    color: G_VIB   },
          { label: "Verification coverage", value: "68%",   color: P_LIGHT },
          { label: "Unserved farmers",      value: "4,218", color: R_LIGHT  },
          { label: "Portfolio (KES M)",     value: "142.6", color: GOLD    },
        ].map(({ label, value, color }) => (
          <motion.div key={label} variants={ITEM} whileHover={{ y: -3 }} transition={{ duration: 0.2 }}
            style={{ ...gl(0.05), padding: 20 }}>
            <p style={{ fontFamily: "'Anton', sans-serif", color, fontSize: "1.8rem", lineHeight: 1 }}>{value}</p>
            <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "0.95rem", marginTop: 4 }}>{label}</p>
          </motion.div>
        ))}
      </motion.div>

      <div className="grid md:grid-cols-2 gap-5">
        <GCard className="p-5">
          <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 2 }}>
            Portfolio Growth
          </p>
          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "0.95rem", marginBottom: 20 }}>
            Cumulative loan value disbursed — KES Millions, 2024
          </p>
          <ResponsiveContainer width="100%" height={210}>
            <AreaChart data={portfolioTrend}>
              <defs>
                <linearGradient id="portG" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={G_VIB} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={G_VIB} stopOpacity={0}    />
                </linearGradient>
              </defs>
              <XAxis dataKey="month" tick={TICK} axisLine={false} tickLine={false} />
              <YAxis tick={TICK} axisLine={false} tickLine={false} unit="M" />
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <Tooltip contentStyle={TIP} />
              <Area type="monotone" dataKey="value" stroke={G_VIB} strokeWidth={2.5} fill="url(#portG)" name="KES M" />
            </AreaChart>
          </ResponsiveContainer>
        </GCard>

        <GCard className="p-5">
          <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 2 }}>
            Approval Trend
          </p>
          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "0.95rem", marginBottom: 20 }}>
            Monthly loan decisions across the portfolio
          </p>
          <ResponsiveContainer width="100%" height={210}>
            <LineChart data={approvalTrend}>
              <XAxis dataKey="month" tick={TICK} axisLine={false} tickLine={false} />
              <YAxis tick={TICK} axisLine={false} tickLine={false} />
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <Tooltip contentStyle={TIP} />
              <Line type="monotone" dataKey="approved" stroke={G_VIB}  strokeWidth={2.5} dot={{ fill: G_VIB,  r: 3, strokeWidth: 0 }} name="Approved" />
              <Line type="monotone" dataKey="rejected" stroke={R_LIGHT} strokeWidth={2.5} dot={{ fill: R_LIGHT, r: 3, strokeWidth: 0 }} name="Rejected" />
              <Line type="monotone" dataKey="pending"  stroke={GOLD}   strokeWidth={2.5} dot={{ fill: GOLD,   r: 3, strokeWidth: 0 }} name="Pending"  />
            </LineChart>
          </ResponsiveContainer>
        </GCard>
      </div>

      <GCard className="p-5">
        <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 2 }}>
          Verification Coverage
        </p>
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "0.95rem", marginBottom: 20 }}>
          Percentage of farmer profiles with each data type verified
        </p>
        <ResponsiveContainer width="100%" height={190}>
          <BarChart data={verifCoverage} layout="vertical" barGap={2}>
            <XAxis type="number" tick={TICK} axisLine={false} tickLine={false} unit="%" />
            <YAxis type="category" dataKey="category" tick={{ ...TICK, fill: "rgba(255,255,255,0.55)" }} axisLine={false} tickLine={false} width={80} />
            <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
            <Tooltip contentStyle={TIP} />
            <Bar dataKey="verified"   fill={G_VIB}                  radius={[0,4,4,0]} name="Verified %"   stackId="a" />
            <Bar dataKey="unverified" fill="rgba(255,255,255,0.05)" radius={[0,4,4,0]} name="Unverified %" stackId="a" />
          </BarChart>
        </ResponsiveContainer>
      </GCard>

      <GCard className="p-5">
        <div className="flex items-center justify-between mb-5">
          <div>
            <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.05em", textTransform: "uppercase" }}>
              Missing Verification
            </p>
            <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "0.95rem" }}>
              High priority — unserved but potentially eligible farmers
            </p>
          </div>
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
            style={{ ...gl(0.05), color: G_VIB }}>
            <Download size={12} /> Export CSV
          </motion.button>
        </div>
        <div className="overflow-x-auto">
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["Farmer", "Location", "Crop", "Missing data", "Risk score", "Action"].map(h => (
                  <th key={h} style={{ textAlign: "left", paddingBottom: 12, paddingRight: 16, fontSize: 10, fontWeight: 600, color: "rgba(255,255,255,0.3)", textTransform: "uppercase", letterSpacing: "0.08em", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(farmers ?? []).filter(f => f.completeness < 80).map((f, i) => {
                const missing = (f.verifications ?? []).filter((v: any) => v.status !== "Verified").map((v: any) => v.type);
                return (
                  <motion.tr key={f.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.08, duration: 0.4 }}
                    style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}
                  >
                    <td style={{ padding: "13px 16px 13px 0", fontSize: 13, fontWeight: 600, color: "#fff" }}>{f.name}</td>
                    <td style={{ padding: "13px 16px 13px 0", fontSize: 12, color: "rgba(255,255,255,0.4)" }}>{f.location}</td>
                    <td style={{ padding: "13px 16px 13px 0", fontSize: 12, color: "rgba(255,255,255,0.4)" }}>{f.crop}</td>
                    <td style={{ padding: "13px 16px 13px 0" }}>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {missing.map((m: string) => (
                          <span key={m} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 20, background: `${R_LIGHT}12`, color: R_LIGHT, border: `1px solid ${R_LIGHT}25` }}>{m}</span>
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: "13px 16px 13px 0" }}>
                      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, fontSize: 13, color: riskColor(f.riskScore) }}>{f.riskScore}</span>
                    </td>
                    <td style={{ padding: "13px 0 13px 0" }}>
                      <button style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600, color: P_LIGHT }}>
                        Request data
                      </button>
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </GCard>
    </motion.div>
  );
}


// ── SIDEBAR ───────────────────────────────────────────────────────────────────
function Sidebar({ page, onNav, role, onLogout, collapsed }: {
  page: string; onNav: (p: string) => void; role: string; onLogout: () => void; collapsed: boolean;
}) {
  const officerItems = [
    { id: "dashboard", label: "Dashboard",  Icon: LayoutDashboard },
    { id: "farmers",   label: "Farmers",    Icon: Users           },
    { id: "analytics", label: "Analytics",  Icon: BarChart3       },
    { id: "settings",  label: "Settings",   Icon: Settings        },
  ];
  const farmerItems = [{ id: "myprofile", label: "My Profile", Icon: UserCheck }];
  const items = role === "officer" ? officerItems : farmerItems;

  return (
    <motion.aside
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
      style={{
        width: collapsed ? 64 : 220,
        transition: "width 0.3s ease",
        flexShrink: 0, display: "flex", flexDirection: "column", minHeight: "100vh",
        background: "rgba(0,0,0,0.55)", backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)",
        borderRight: "1px solid rgba(255,255,255,0.06)", position: "relative", zIndex: 10,
      }}
    >
      <div style={{ padding: collapsed ? "22px 0" : "22px 18px", borderBottom: "1px solid rgba(255,255,255,0.05)", display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "flex-start", gap: 10 }}>
        <Shield size={17} style={{ color: G_VIB, flexShrink: 0 }} />
        {!collapsed && <span style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: 16, letterSpacing: "0.1em", whiteSpace: "nowrap" }}>VERIFARM</span>}
      </div>

      {!collapsed && (
        <div style={{ padding: "10px 14px" }}>
          <div style={{ fontSize: 10, fontWeight: 700, padding: "4px 10px", borderRadius: 20, textAlign: "center", background: `${G_VIB}12`, color: G_VIB, textTransform: "uppercase", letterSpacing: "0.08em" }}>
            {role === "officer" ? "Credit Officer" : "Farmer"}
          </div>
        </div>
      )}

      <nav style={{ flex: 1, padding: "8px 8px" }}>
        {items.map(({ id, label, Icon }) => {
          const active = page === id;
          return (
            <motion.button key={id} onClick={() => onNav(id)} whileHover={{ x: 2 }} transition={{ duration: 0.16 }}
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: 10,
                padding: collapsed ? "11px 0" : "10px 12px",
                justifyContent: collapsed ? "center" : "flex-start",
                borderRadius: 10, marginBottom: 2,
                background: active ? `${G_VIB}12` : "transparent",
                color: active ? G_VIB : "rgba(255,255,255,0.45)",
                borderLeft: active && !collapsed ? `2.5px solid ${G_VIB}` : "2.5px solid transparent",
                border: "none", cursor: "pointer",
                fontFamily: "'Inter', sans-serif", fontSize: 13, fontWeight: active ? 600 : 400,
                transition: "background 0.2s, color 0.2s",
              }}
              title={collapsed ? label : undefined}
            >
              <Icon size={16} style={{ flexShrink: 0 }} />
              {!collapsed && label}
            </motion.button>
          );
        })}
      </nav>

      <div style={{ padding: "12px 8px", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
        <motion.button onClick={onLogout} whileHover={{ x: 2 }}
          style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, justifyContent: collapsed ? "center" : "flex-start", padding: collapsed ? "10px 0" : "10px 12px", borderRadius: 10, background: "none", border: "none", cursor: "pointer", color: "rgba(255,255,255,0.3)", fontSize: 13, fontFamily: "'Inter', sans-serif" }}
          title={collapsed ? "Sign out" : undefined}
        >
          <LogOut size={15} /> {!collapsed && "Sign out"}
        </motion.button>
      </div>
    </motion.aside>
  );
}

// ── TOPBAR ────────────────────────────────────────────────────────────────────
function Topbar({ title, sub, onToggle }: { title: string; sub?: string; onToggle: () => void }) {
  return (
    <div style={{ height: 60, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 24px", background: "rgba(5,16,14,0.85)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", borderBottom: "1px solid rgba(255,255,255,0.05)", flexShrink: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <motion.button onClick={onToggle} whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}
          style={{ background: "none", border: "none", cursor: "pointer", color: "rgba(255,255,255,0.45)", display: "flex", alignItems: "center" }}>
          <Menu size={18} />
        </motion.button>
        <div>
          <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.95rem", letterSpacing: "0.05em", textTransform: "uppercase", lineHeight: 1.1 }}>{title}</p>
          {sub && <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.35)", fontSize: "0.8rem" }}>{sub}</p>}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <motion.button whileHover={{ scale: 1.05 }} style={{ position: "relative", background: "none", border: "none", cursor: "pointer", color: "rgba(255,255,255,0.45)", padding: 6, display: "flex" }}>
          <Bell size={17} />
          <span style={{ position: "absolute", top: 5, right: 5, width: 6, height: 6, borderRadius: "50%", background: R_LIGHT }} />
        </motion.button>
        <motion.div whileHover={{ scale: 1.05 }}
          style={{ width: 32, height: 32, borderRadius: "50%", background: `${G_VIB}20`, border: `1.5px solid ${G_VIB}40`, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontFamily: "'Anton', sans-serif", color: G_VIB, fontSize: 11, letterSpacing: "0.02em" }}>GM</span>
        </motion.div>
      </div>
    </div>
  );
}

// ── MOBILE BOTTOM NAV ─────────────────────────────────────────────────────────
function BottomNav({ page, onNav, role }: { page: string; onNav: (p: string) => void; role: string }) {
  const items = role === "officer"
    ? [
        { id: "dashboard", label: "Home",      Icon: LayoutDashboard },
        { id: "farmers",   label: "Farmers",   Icon: Users           },
        { id: "analytics", label: "Analytics", Icon: BarChart3       },
        { id: "settings",  label: "Settings",  Icon: Settings        },
      ]
    : [{ id: "myprofile", label: "Profile", Icon: UserCheck }];

  return (
    <div className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around px-2 py-2"
      style={{ background: "rgba(5,16,14,0.97)", backdropFilter: "blur(20px)", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
      {items.map(({ id, label, Icon }) => {
        const active = page === id;
        return (
          <button key={id} onClick={() => onNav(id)}
            style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2, padding: "6px 4px", background: "none", border: "none", cursor: "pointer", color: active ? G_VIB : "rgba(255,255,255,0.35)" }}>
            <Icon size={18} />
            <span style={{ fontSize: 9, fontWeight: 600, fontFamily: "'Inter', sans-serif", textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

// ── ROOT APP ──────────────────────────────────────────────────────────────────
const PAGE_TITLES: Record<string, { title: string; sub?: string }> = {
  dashboard: { title: "Dashboard",  sub: "Overview of your credit portfolio"        },
  farmers:   { title: "Farmers",    sub: "Review and approve farmer applications"   },
  analytics: { title: "Analytics",  sub: "Cooperative and portfolio-level insights" },
  settings:  { title: "Settings"                                                     },
  myprofile: { title: "My Profile", sub: "Your verified VeriFarm profile"           },
};

export default function App() {
  const [role, setRole]           = useState<string | null>(null);
  const [page, setPage]           = useState("dashboard");
  const [collapsed, setCollapsed] = useState(false);
  const [farmers, setFarmers]     = useState<any[]>([]);
  const [farmersLoading, setFarmersLoading] = useState(true);
  const [profileId, setProfileId] = useState<any>(null);

  useEffect(() => {
    fetchAllFarmers()
      .then(setFarmers)
      .catch(console.error)
      .finally(() => setFarmersLoading(false));
  }, []);

  if (!role) {
    return (
      <div style={{ minHeight: "100vh", background: "linear-gradient(135deg, #071410 0%, #0B1F16 50%, #060d09 100%)", position: "relative", overflow: "hidden", fontFamily: "'Inter', sans-serif" }}>
        <AmbientBg />
        <div style={{ position: "relative", zIndex: 1 }}>
          <LoginPage onLogin={(r) => { setRole(r); setPage(r === "farmer" ? "myprofile" : "dashboard"); }} />
        </div>
      </div>
    );
  }

  const renderContent = () => {
    if (farmersLoading) {
      return (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "60vh", flexDirection: "column", gap: 16 }}>
          <div className="animate-pulse" style={{ width: 56, height: 56, borderRadius: "50%", background: `${G_VIB}20`, border: `1px solid ${G_VIB}30` }} />
          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "1.2rem" }}>Loading farmers…</p>
        </div>
      );
    }
    if (page === "dashboard")  return <DashboardOverview farmers={farmers} onViewFarmer={(id) => { setProfileId(id); setPage("farmers"); }} />;
    if (page === "farmers") {
      if (profileId !== null)  return <FarmerProfile farmers={farmers} farmerId={profileId} onBack={() => setProfileId(null)} />;
      return <FarmersList farmers={farmers} onViewFarmer={(id) => setProfileId(id)} />;
    }
    if (page === "analytics")  return <AnalyticsPage farmers={farmers} />;
    if (page === "myprofile") {
    const hasCompletedOnboarding = localStorage.getItem("verifarm_onboarded") === "true";
    const farmerId = localStorage.getItem("verifarm_farmer_id");
    return hasCompletedOnboarding && farmerId
      ? <FarmerSelfView farmerId={farmerId} />
      : <FarmerOnboarding onComplete={(id) => {
          localStorage.setItem("verifarm_onboarded", "true");
          if (id) localStorage.setItem("verifarm_farmer_id", id);
          setPage("myprofile");
        }} />;
    }
    return (
      <div style={{ padding: 40, textAlign: "center" }}>
        <Settings size={36} style={{ color: "rgba(255,255,255,0.2)", margin: "0 auto 12px" }} />
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.3)", fontSize: "1.1rem" }}>Settings coming soon</p>
      </div>
    );
  };

  const pt = PAGE_TITLES[page] ?? { title: "VeriFarm" };

  return (
    <div style={{ minHeight: "100vh", background: "linear-gradient(135deg, #071410 0%, #0B1F16 50%, #060d09 100%)", position: "relative", overflow: "hidden", fontFamily: "'Inter', sans-serif" }}>
      <AmbientBg />
      <div style={{ position: "relative", zIndex: 1, display: "flex", minHeight: "100vh" }}>
        <div className="hidden md:block">
          <Sidebar page={page} onNav={(p) => { setPage(p); setProfileId(null); }} role={role} onLogout={() => setRole(null)} collapsed={collapsed} />
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          <Topbar title={pt.title} sub={pt.sub} onToggle={() => setCollapsed(c => !c)} />
          <main style={{ flex: 1, overflowY: "auto", paddingBottom: 64 }}>
            <motion.div key={`${page}-${profileId}`} variants={PAGE} initial="hidden" animate="show">
              {renderContent()}
            </motion.div>
          </main>
        </div>
        <BottomNav page={page} onNav={(p) => { setPage(p); setProfileId(null); }} role={role} />
      </div>
    </div>
  );
}
