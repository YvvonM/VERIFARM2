/**
 * VeriFarm — Farmer Onboarding Wizard
 * ====================================
 * With language picker + streaming translation via Featherless/Gemma 4
 */

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Shield, UserCheck, MapPin, Sprout, CreditCard,
  CheckCircle2, AlertTriangle, ArrowRight, ArrowLeft,
  Loader2, Leaf, Landmark, Satellite, Phone, User, Globe,
  CheckIcon, X, Languages
} from "lucide-react";

const G_VIB  = "#4ADE80";
const GOLD   = "#F4A261";
const PURPLE = "#7C3AED";
const R_LIGHT = "#F87171";
const SKY    = "#38BDF8";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────
interface OnboardingData {
  name: string; phone: string; country: string; location: string; consent: boolean;
  nationalId: string;
  selfReportedHectares: string; latitude: string; longitude: string; useSatellite: boolean;
  estimatedTons: string; season: string; cropType: string;
  consentCreditCheck: boolean;
  farmerId: string | null; currentStep: string; status: string | null;
  riskScore: number | null; completeness: number | null; offers: any[]; hasConflicts: boolean;
}

interface StepProps {
  data: OnboardingData;
  onUpdate: (patch: Partial<OnboardingData>) => void;
  onNext: () => void;
  onBack?: () => void;
  isLoading?: boolean;
  error?: string | null;
  t: Record<string, string>;
}

type Strings = Record<string, string>;

const SUPPORTED_LANGUAGES = ["English", "Swahili", "Yoruba", "Hausa", "Igbo"];

const LANGUAGE_FLAGS: Record<string, string> = {
  English: "🌍", Swahili: "🇰🇪", Yoruba: "🇳🇬", Hausa: "🇳🇬", Igbo: "🇳🇬",
};

const DEFAULT_STRINGS: Strings = {
  step_register: "Register", step_identity: "Identity", step_land: "Land",
  step_production: "Production", step_credit: "Credit",
  register_title: "Create Your Profile",
  register_subtitle: "Start your VeriFarm verification journey",
  field_full_name: "Full Name", field_full_name_placeholder: "e.g. John Kamau",
  field_phone: "Phone Number", field_phone_placeholder: "+254 712 345 678",
  field_country: "Country", field_country_placeholder: "Kenya",
  field_location: "Location (Town/Village)", field_location_placeholder: "e.g. Kirinyaga",
  consent_label: "I consent to share my data with VeriFarm partners",
  consent_sub: "This includes cooperatives, lenders, and insurers who need verified data to serve you better.",
  btn_start: "Start Verification", btn_creating: "Creating profile...",
  identity_title: "Verify Your Identity",
  identity_subtitle: "We check with the national registry",
  field_national_id: "National ID / BVN", field_national_id_placeholder: "Enter your ID number",
  btn_verify_identity: "Verify Identity", btn_verifying: "Verifying...",
  land_title: "Your Farm Size",
  land_subtitle: "Self-report + optional satellite cross-check",
  field_farm_size: "Farm Size (hectares)", field_farm_size_placeholder: "e.g. 2.5",
  satellite_label: "Cross-check with satellite imagery",
  satellite_sub: "We use Sentinel-2 data to verify your farm size.",
  field_latitude: "Latitude", field_longitude: "Longitude",
  btn_continue: "Continue", btn_checking: "Checking...",
  production_title: "Production Estimate",
  production_subtitle: "Expected harvest for this season",
  field_estimated_tons: "Estimated Production (tons)", field_estimated_tons_placeholder: "e.g. 5.0",
  field_season: "Growing Season", field_season_placeholder: "e.g. 2024 Long Rains",
  field_crop: "Primary Crop", field_crop_placeholder: "e.g. Maize",
  btn_saving: "Saving...",
  credit_title: "Credit History", credit_subtitle: "Final step — check your credit standing",
  credit_consent_label: "I consent to a credit bureau check",
  credit_consent_sub: "This helps lenders offer you better rates. No impact on your score.",
  btn_complete: "Complete Verification", btn_checking_credit: "Checking...",
  result_title_complete: "Verification Complete", result_title_submitted: "Verification Submitted",
  result_subtitle_approved: "Your profile is verified and ready for offers!",
  result_subtitle_pending: "Your profile is under review. Check back soon.",
  result_subtitle_conflict: "Some claims need manual review. We'll notify you.",
  result_risk_score: "Credit Score", result_completeness: "Complete",
  result_offers_title: "Pre-qualified Offers",
  btn_go_to_profile: "Go to My Profile", btn_verify_another: "Verify Another Farmer",
  error_generic: "Something went wrong. Please try again.",
  error_phone_exists: "This phone number is already registered.",
  error_not_found: "Farmer not found. Please register first.",
  error_consent_required: "Consent is required to proceed.",
  back: "Back", next: "Next",
};

const INITIAL_DATA: OnboardingData = {
  name: "", phone: "", country: "", location: "", consent: false,
  nationalId: "", selfReportedHectares: "", latitude: "", longitude: "",
  useSatellite: true, estimatedTons: "", season: "", cropType: "",
  consentCreditCheck: false, farmerId: null, currentStep: "identity",
  status: null, riskScore: null, completeness: null, offers: [], hasConflicts: false,
};

// ── Glassmorphism ─────────────────────────────────────────────────────────────
const gl = (alpha = 0.05, blur = 20): React.CSSProperties => ({
  background: `rgba(255,255,255,${alpha})`,
  backdropFilter: `blur(${blur}px)`,
  WebkitBackdropFilter: `blur(${blur}px)`,
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 16,
  boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
});

// ── Language Picker Screen ────────────────────────────────────────────────────
function LanguagePicker({ onSelect }: { onSelect: (lang: string) => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="text-center"
    >
      <div className="inline-flex items-center justify-center rounded-2xl mb-4"
        style={{ width: 56, height: 56, background: `${G_VIB}12`, border: `1px solid ${G_VIB}25` }}>
        <Languages size={24} style={{ color: G_VIB }} />
      </div>
      <h2 style={{
        fontFamily: "'Anton', sans-serif", color: "#fff",
        fontSize: "1.4rem", letterSpacing: "0.04em", textTransform: "uppercase",
      }}>
        Choose Your Language
      </h2>
      <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "1.05rem", marginTop: 4, marginBottom: 28 }}>
        Select the language you are most comfortable with
      </p>

      <div className="flex flex-col gap-3">
        {SUPPORTED_LANGUAGES.map((lang) => (
          <motion.button
            key={lang}
            onClick={() => onSelect(lang)}
            whileHover={{ scale: 1.03, boxShadow: `0 0 20px ${G_VIB}30` }}
            whileTap={{ scale: 0.97 }}
            className="w-full py-4 rounded-xl text-base font-semibold flex items-center gap-4 px-5"
            style={{
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.12)",
              color: "#fff",
              cursor: "pointer",
            }}
          >
            <span style={{ fontSize: "1.5rem" }}>{LANGUAGE_FLAGS[lang]}</span>
            <span>{lang}</span>
            {lang === "English" && (
              <span style={{
                marginLeft: "auto", fontSize: 11, color: "rgba(255,255,255,0.3)",
                background: "rgba(255,255,255,0.06)", padding: "2px 8px", borderRadius: 20,
              }}>
                Default
              </span>
            )}
          </motion.button>
        ))}
      </div>
    </motion.div>
  );
}

// ── Translation indicator ─────────────────────────────────────────────────────
function TranslatingBadge({ language, progress }: { language: string; progress: number }) {
  if (progress >= 100) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg"
      style={{ background: `${G_VIB}10`, border: `1px solid ${G_VIB}25` }}
    >
      <Loader2 size={12} className="animate-spin" style={{ color: G_VIB }} />
      <span style={{ fontSize: 12, color: G_VIB }}>
        Translating to {language}... {Math.round(progress)}%
      </span>
      <div className="flex-1 h-1 rounded-full ml-2" style={{ background: "rgba(255,255,255,0.08)" }}>
        <div className="h-1 rounded-full transition-all" style={{ width: `${progress}%`, background: G_VIB }} />
      </div>
    </motion.div>
  );
}

// ── Reusable components ───────────────────────────────────────────────────────
function StepIndicator({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-8">
      {steps.map((label, i) => {
        const done = i < current; const active = i === current;
        return (
          <div key={label} className="flex items-center gap-2">
            <div className="flex items-center justify-center rounded-full text-xs font-bold transition-all"
              style={{
                width: 28, height: 28,
                background: done ? G_VIB : active ? `${G_VIB}20` : "rgba(255,255,255,0.06)",
                color: done ? "#071410" : active ? G_VIB : "rgba(255,255,255,0.3)",
                border: active ? `2px solid ${G_VIB}` : "2px solid transparent",
              }}>
              {done ? <CheckIcon size={14} /> : i + 1}
            </div>
            <span className="text-xs font-medium hidden sm:block"
              style={{ color: active ? G_VIB : done ? "rgba(255,255,255,0.6)" : "rgba(255,255,255,0.25)" }}>
              {label}
            </span>
            {i < steps.length - 1 && (
              <div className="w-6 h-px mx-1" style={{ background: done ? G_VIB : "rgba(255,255,255,0.08)" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function VFInput({ label, value, onChange, type = "text", placeholder, required = false, icon: Icon }: {
  label: string; value: string; onChange: (v: string) => void;
  type?: string; placeholder?: string; required?: boolean; icon?: React.ElementType;
}) {
  return (
    <div className="mb-4">
      <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.5)", marginBottom: 6, letterSpacing: "0.06em", textTransform: "uppercase" }}>
        {label} {required && <span style={{ color: R_LIGHT }}>*</span>}
      </label>
      <div style={{ position: "relative" }}>
        {Icon && <Icon size={14} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "rgba(255,255,255,0.25)" }} />}
        <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} required={required}
          style={{ width: "100%", padding: "11px 14px", paddingLeft: Icon ? 36 : 14, borderRadius: 10, background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.12)", color: "#fff", fontSize: 14, outline: "none", fontFamily: "'Inter', sans-serif", boxSizing: "border-box" }} />
      </div>
    </div>
  );
}

function VFCheckbox({ checked, onChange, label, sub }: { checked: boolean; onChange: (v: boolean) => void; label: string; sub?: string; }) {
  return (
    <div onClick={() => onChange(!checked)} className="flex items-start gap-3 p-4 rounded-xl cursor-pointer transition-all"
      style={{ ...gl(0.04), border: checked ? `1px solid ${G_VIB}40` : "1px solid rgba(255,255,255,0.08)", background: checked ? `${G_VIB}08` : undefined }}>
      <div className="flex items-center justify-center rounded-md shrink-0 mt-0.5"
        style={{ width: 20, height: 20, border: checked ? `2px solid ${G_VIB}` : "2px solid rgba(255,255,255,0.2)", background: checked ? G_VIB : "transparent" }}>
        {checked && <CheckIcon size={12} color="#071410" strokeWidth={3} />}
      </div>
      <div>
        <p className="text-sm font-medium text-white">{label}</p>
        {sub && <p className="text-xs mt-1" style={{ color: "rgba(255,255,255,0.4)" }}>{sub}</p>}
      </div>
    </div>
  );
}

function ErrorBanner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-3 p-4 rounded-xl mb-4"
      style={{ background: `${R_LIGHT}12`, border: `1px solid ${R_LIGHT}30` }}>
      <AlertTriangle size={16} style={{ color: R_LIGHT }} />
      <p className="text-sm flex-1" style={{ color: R_LIGHT }}>{message}</p>
      <button onClick={onDismiss} style={{ background: "none", border: "none", cursor: "pointer", color: R_LIGHT }}><X size={14} /></button>
    </motion.div>
  );
}

// ── Steps ─────────────────────────────────────────────────────────────────────
function StepRegister({ data, onUpdate, onNext, isLoading, error, t }: StepProps) {
  const canProceed = data.name.trim().length >= 2 && data.phone.trim().length >= 8 && data.country.trim().length > 0 && data.consent;
  return (
    <div>
      <div className="text-center mb-6">
        <div className="inline-flex items-center justify-center rounded-2xl mb-4"
          style={{ width: 56, height: 56, background: `${G_VIB}12`, border: `1px solid ${G_VIB}25` }}>
          <Shield size={24} style={{ color: G_VIB }} />
        </div>
        <h2 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.4rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>{t.register_title}</h2>
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "1.05rem", marginTop: 4 }}>{t.register_subtitle}</p>
      </div>
      {error && <ErrorBanner message={error} onDismiss={() => {}} />}
      <VFInput label={t.field_full_name} value={data.name} onChange={(v) => onUpdate({ name: v })} placeholder={t.field_full_name_placeholder} required icon={User} />
      <VFInput label={t.field_phone} value={data.phone} onChange={(v) => onUpdate({ phone: v })} placeholder={t.field_phone_placeholder} required icon={Phone} />
      <VFInput label={t.field_country} value={data.country} onChange={(v) => onUpdate({ country: v })} placeholder={t.field_country_placeholder} required icon={Globe} />
      <VFInput label={t.field_location} value={data.location} onChange={(v) => onUpdate({ location: v })} placeholder={t.field_location_placeholder} icon={MapPin} />
      <div className="mt-4">
        <VFCheckbox checked={data.consent} onChange={(v) => onUpdate({ consent: v })} label={t.consent_label} sub={t.consent_sub} />
      </div>
      <motion.button onClick={onNext} disabled={!canProceed || isLoading}
        whileHover={canProceed ? { scale: 1.02, boxShadow: `0 0 28px ${G_VIB}45` } : {}}
        whileTap={canProceed ? { scale: 0.98 } : {}}
        className="w-full mt-6 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all"
        style={{ background: canProceed ? G_VIB : "rgba(255,255,255,0.08)", color: canProceed ? "#071410" : "rgba(255,255,255,0.3)", border: "none", cursor: canProceed ? "pointer" : "not-allowed" }}>
        {isLoading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
        {isLoading ? t.btn_creating : t.btn_start}
      </motion.button>
    </div>
  );
}

function StepIdentity({ data, onUpdate, onNext, onBack, isLoading, error, t }: StepProps) {
  const canProceed = data.nationalId.trim().length >= 5;
  return (
    <div>
      <div className="text-center mb-6">
        <div className="inline-flex items-center justify-center rounded-2xl mb-4"
          style={{ width: 56, height: 56, background: `${SKY}12`, border: `1px solid ${SKY}25` }}>
          <UserCheck size={24} style={{ color: SKY }} />
        </div>
        <h2 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.4rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>{t.identity_title}</h2>
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "1.05rem", marginTop: 4 }}>{t.identity_subtitle}</p>
      </div>
      {error && <ErrorBanner message={error} onDismiss={() => {}} />}
      <VFInput label={t.field_national_id} value={data.nationalId} onChange={(v) => onUpdate({ nationalId: v })} placeholder={t.field_national_id_placeholder} required icon={Landmark} />
      <div className="flex gap-3 mt-6">
        {onBack && (
          <motion.button onClick={onBack} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            className="flex-1 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.6)", border: "1px solid rgba(255,255,255,0.1)" }}>
            <ArrowLeft size={16} /> {t.back}
          </motion.button>
        )}
        <motion.button onClick={onNext} disabled={!canProceed || isLoading}
          whileHover={canProceed ? { scale: 1.02, boxShadow: `0 0 28px ${SKY}45` } : {}}
          whileTap={canProceed ? { scale: 0.98 } : {}}
          className="flex-[2] py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all"
          style={{ background: canProceed ? SKY : "rgba(255,255,255,0.08)", color: canProceed ? "#071410" : "rgba(255,255,255,0.3)", border: "none", cursor: canProceed ? "pointer" : "not-allowed" }}>
          {isLoading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
          {isLoading ? t.btn_verifying : t.btn_verify_identity}
        </motion.button>
      </div>
    </div>
  );
}

function StepLand({ data, onUpdate, onNext, onBack, isLoading, error, t }: StepProps) {
  const canProceed = parseFloat(data.selfReportedHectares) > 0;
  return (
    <div>
      <div className="text-center mb-6">
        <div className="inline-flex items-center justify-center rounded-2xl mb-4"
          style={{ width: 56, height: 56, background: `${GOLD}12`, border: `1px solid ${GOLD}25` }}>
          <MapPin size={24} style={{ color: GOLD }} />
        </div>
        <h2 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.4rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>{t.land_title}</h2>
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "1.05rem", marginTop: 4 }}>{t.land_subtitle}</p>
      </div>
      {error && <ErrorBanner message={error} onDismiss={() => {}} />}
      <VFInput label={t.field_farm_size} value={data.selfReportedHectares} onChange={(v) => onUpdate({ selfReportedHectares: v })} placeholder={t.field_farm_size_placeholder} type="number" required icon={Leaf} />
      <div className="mt-4 mb-4">
        <VFCheckbox checked={data.useSatellite} onChange={(v) => onUpdate({ useSatellite: v })} label={t.satellite_label} sub={t.satellite_sub} />
      </div>
      {data.useSatellite && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="grid grid-cols-2 gap-3 mb-4">
          <VFInput label={t.field_latitude} value={data.latitude} onChange={(v) => onUpdate({ latitude: v })} placeholder="-0.6590" type="number" icon={Satellite} />
          <VFInput label={t.field_longitude} value={data.longitude} onChange={(v) => onUpdate({ longitude: v })} placeholder="37.3050" type="number" icon={Satellite} />
        </motion.div>
      )}
      <div className="flex gap-3 mt-6">
        {onBack && (
          <motion.button onClick={onBack} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            className="flex-1 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.6)", border: "1px solid rgba(255,255,255,0.1)" }}>
            <ArrowLeft size={16} /> {t.back}
          </motion.button>
        )}
        <motion.button onClick={onNext} disabled={!canProceed || isLoading}
          whileHover={canProceed ? { scale: 1.02, boxShadow: `0 0 28px ${GOLD}45` } : {}}
          whileTap={canProceed ? { scale: 0.98 } : {}}
          className="flex-[2] py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all"
          style={{ background: canProceed ? GOLD : "rgba(255,255,255,0.08)", color: canProceed ? "#071410" : "rgba(255,255,255,0.3)", border: "none", cursor: canProceed ? "pointer" : "not-allowed" }}>
          {isLoading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
          {isLoading ? t.btn_checking : t.btn_continue}
        </motion.button>
      </div>
    </div>
  );
}

function StepProduction({ data, onUpdate, onNext, onBack, isLoading, error, t }: StepProps) {
  const canProceed = parseFloat(data.estimatedTons) > 0 && data.season.trim() && data.cropType.trim();
  return (
    <div>
      <div className="text-center mb-6">
        <div className="inline-flex items-center justify-center rounded-2xl mb-4"
          style={{ width: 56, height: 56, background: `${PURPLE}12`, border: `1px solid ${PURPLE}25` }}>
          <Sprout size={24} style={{ color: PURPLE }} />
        </div>
        <h2 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.4rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>{t.production_title}</h2>
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "1.05rem", marginTop: 4 }}>{t.production_subtitle}</p>
      </div>
      {error && <ErrorBanner message={error} onDismiss={() => {}} />}
      <VFInput label={t.field_estimated_tons} value={data.estimatedTons} onChange={(v) => onUpdate({ estimatedTons: v })} placeholder={t.field_estimated_tons_placeholder} type="number" required icon={Sprout} />
      <VFInput label={t.field_season} value={data.season} onChange={(v) => onUpdate({ season: v })} placeholder={t.field_season_placeholder} required />
      <VFInput label={t.field_crop} value={data.cropType} onChange={(v) => onUpdate({ cropType: v })} placeholder={t.field_crop_placeholder} required icon={Leaf} />
      <div className="flex gap-3 mt-6">
        {onBack && (
          <motion.button onClick={onBack} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            className="flex-1 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.6)", border: "1px solid rgba(255,255,255,0.1)" }}>
            <ArrowLeft size={16} /> {t.back}
          </motion.button>
        )}
        <motion.button onClick={onNext} disabled={!canProceed || isLoading}
          whileHover={canProceed ? { scale: 1.02, boxShadow: `0 0 28px ${PURPLE}45` } : {}}
          whileTap={canProceed ? { scale: 0.98 } : {}}
          className="flex-[2] py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all"
          style={{ background: canProceed ? PURPLE : "rgba(255,255,255,0.08)", color: canProceed ? "#fff" : "rgba(255,255,255,0.3)", border: "none", cursor: canProceed ? "pointer" : "not-allowed" }}>
          {isLoading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
          {isLoading ? t.btn_saving : t.btn_continue}
        </motion.button>
      </div>
    </div>
  );
}

function StepCredit({ data, onUpdate, onNext, onBack, isLoading, error, t }: StepProps) {
  return (
    <div>
      <div className="text-center mb-6">
        <div className="inline-flex items-center justify-center rounded-2xl mb-4"
          style={{ width: 56, height: 56, background: `${G_VIB}12`, border: `1px solid ${G_VIB}25` }}>
          <CreditCard size={24} style={{ color: G_VIB }} />
        </div>
        <h2 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.4rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>{t.credit_title}</h2>
        <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "1.05rem", marginTop: 4 }}>{t.credit_subtitle}</p>
      </div>
      {error && <ErrorBanner message={error} onDismiss={() => {}} />}
      <div className="mt-4 mb-6">
        <VFCheckbox checked={data.consentCreditCheck} onChange={(v) => onUpdate({ consentCreditCheck: v })} label={t.credit_consent_label} sub={t.credit_consent_sub} />
      </div>
      <div className="flex gap-3 mt-6">
        {onBack && (
          <motion.button onClick={onBack} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            className="flex-1 py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.6)", border: "1px solid rgba(255,255,255,0.1)" }}>
            <ArrowLeft size={16} /> {t.back}
          </motion.button>
        )}
        <motion.button onClick={onNext} disabled={!data.consentCreditCheck || isLoading}
          whileHover={data.consentCreditCheck ? { scale: 1.02, boxShadow: `0 0 28px ${G_VIB}45` } : {}}
          whileTap={data.consentCreditCheck ? { scale: 0.98 } : {}}
          className="flex-[2] py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all"
          style={{ background: data.consentCreditCheck ? G_VIB : "rgba(255,255,255,0.08)", color: data.consentCreditCheck ? "#071410" : "rgba(255,255,255,0.3)", border: "none", cursor: data.consentCreditCheck ? "pointer" : "not-allowed" }}>
          {isLoading ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
          {isLoading ? t.btn_checking_credit : t.btn_complete}
        </motion.button>
      </div>
    </div>
  );
}

function StepResult({ data, onReset, onComplete, t }: { data: OnboardingData; onReset: () => void; onComplete?: () => void; t: Strings }) {
  const statusColor = data.status === "approved" ? G_VIB : data.status === "pending" ? GOLD : R_LIGHT;
  const StatusIcon = data.status === "approved" ? CheckCircle2 : AlertTriangle;
  return (
    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }} className="text-center">
      <div className="inline-flex items-center justify-center rounded-full mb-6"
        style={{ width: 72, height: 72, background: `${statusColor}15`, border: `2px solid ${statusColor}40` }}>
        <StatusIcon size={32} style={{ color: statusColor }} />
      </div>
      <h2 style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "1.6rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>
        {data.status === "approved" ? t.result_title_complete : t.result_title_submitted}
      </h2>
      <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.45)", fontSize: "1.1rem", marginTop: 4 }}>
        {data.status === "approved" ? t.result_subtitle_approved : data.hasConflicts ? t.result_subtitle_conflict : t.result_subtitle_pending}
      </p>
      <div className="grid grid-cols-2 gap-4 mt-8 mb-8">
        <div style={{ ...gl(0.06), padding: "20px 16px" }}>
          <p style={{ fontFamily: "'Anton', sans-serif", color: G_VIB, fontSize: "1.8rem" }}>{data.riskScore ?? "—"}</p>
          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "0.85rem", marginTop: 4 }}>{t.result_risk_score}</p>
        </div>
        <div style={{ ...gl(0.06), padding: "20px 16px" }}>
          <p style={{ fontFamily: "'Anton', sans-serif", color: G_VIB, fontSize: "1.8rem" }}>{data.completeness ?? "—"}%</p>
          <p style={{ fontFamily: "'Caveat', cursive", color: "rgba(255,255,255,0.4)", fontSize: "0.85rem", marginTop: 4 }}>{t.result_completeness}</p>
        </div>
      </div>
      {data.offers?.length > 0 && (
        <div className="text-left mb-8">
          <p style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: "0.9rem", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 12 }}>{t.result_offers_title}</p>
          <div className="space-y-3">
            {data.offers.map((offer: any, i: number) => (
              <div key={i} style={{ ...gl(0.05), padding: 16, borderLeft: `3px solid ${G_VIB}` }}>
                <p className="text-sm font-semibold text-white">{offer.product}</p>
                <p className="text-xs mt-1" style={{ color: "rgba(255,255,255,0.5)" }}>{offer.provider} · {offer.eligibility}</p>
                {offer.max_amount && <p className="text-xs mt-2 font-mono" style={{ color: G_VIB }}>Up to KES {offer.max_amount.toLocaleString()}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="flex gap-3">
        <motion.button onClick={onComplete || onReset} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          className="flex-1 py-3 rounded-xl text-sm font-bold"
          style={{ background: G_VIB, color: "#071410", border: "none", cursor: "pointer" }}>
          {t.btn_go_to_profile}
        </motion.button>
        <motion.button onClick={onReset} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          className="flex-1 py-3 rounded-xl text-sm font-bold"
          style={{ background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.6)", border: "1px solid rgba(255,255,255,0.12)", cursor: "pointer" }}>
          {t.btn_verify_another}
        </motion.button>
      </div>
    </motion.div>
  );
}

// ── MAIN COMPONENT ────────────────────────────────────────────────────────────
const STEPS = (t: Strings) => [t.step_register, t.step_identity, t.step_land, t.step_production, t.step_credit];

export default function FarmerOnboarding({ onComplete }: { onComplete?: (farmerId?: string) => void }) {
  const [screen, setScreen] = useState<"language" | "form">("language");
  const [language, setLanguage] = useState("English");
  const [strings, setStrings] = useState<Strings>({ ...DEFAULT_STRINGS });
  const [translateProgress, setTranslateProgress] = useState(0);
  const [step, setStep] = useState(0);
  const [data, setData] = useState<OnboardingData>({ ...INITIAL_DATA });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const totalKeys = Object.keys(DEFAULT_STRINGS).length;

  const startTranslation = async (lang: string) => {
    if (lang === "English") {
      setStrings({ ...DEFAULT_STRINGS });
      setTranslateProgress(100);
      return;
    }

    setTranslateProgress(0);
    let count = 0;

    try {
      const res = await fetch(`${API_BASE}/api/translate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language: lang }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const payload = JSON.parse(line.slice(6));
              if (payload.done) {
                setTranslateProgress(100);
              } else if (payload.key && payload.value) {
                setStrings((prev) => ({ ...prev, [payload.key]: payload.value }));
                count++;
                setTranslateProgress(Math.round((count / totalKeys) * 100));
              }
            } catch {}
          }
        }
      }
    } catch (err) {
      console.error("Translation stream error:", err);
      // Keep English strings as fallback
    }
  };

  const handleLanguageSelect = (lang: string) => {
    setLanguage(lang);
    setScreen("form");
    startTranslation(lang);
  };

  const updateData = (patch: Partial<OnboardingData>) => {
    setData((prev) => ({ ...prev, ...patch }));
    setError(null);
  };

  const apiCall = async (endpoint: string, body: any) => {
    // Strip undefined/null values before sending
    const cleanBody = Object.fromEntries(
        Object.entries(body).filter(([_, v]) => v !== undefined && v !== null)
    );

    const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanBody),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Request failed (${res.status})`);
    }
    return res.json();
  };

  const handleNext = async () => {
    setIsLoading(true);
    setError(null);
    try {
      if (step === 0) {
        const result = await apiCall("/api/onboarding/register", {
          name: data.name, phone: data.phone, country: data.country,
          location: data.location || undefined, consent: data.consent,
        });
        updateData({ farmerId: result.farmer_id });
        setStep(1);
      } else if (step === 1) {
        await apiCall(`/api/onboarding/${data.phone}/verify-identity`, { national_id: data.nationalId });
        setStep(2);
      } else if (step === 2) {
        const hectares = parseFloat(data.selfReportedHectares);
        const lat = data.latitude?.trim();
        const lon = data.longitude?.trim();

        const body: any = {
            self_reported_hectares: hectares,
            use_satellite: data.useSatellite,
        };
        if (lat) body.latitude = parseFloat(lat);
        if (lon) body.longitude = parseFloat(lon);

        await apiCall(`/api/onboarding/${data.phone}/verify-land`, body);
        setStep(3);

      } else if (step === 3) {
  await apiCall(`/api/onboarding/${data.phone}/verify-production`, {
    estimated_tons: parseFloat(data.estimatedTons),
    season: data.season,
    crop_type: data.cropType,
  });
  setStep(4);
} else if (step === 4) {
  const result = await apiCall(`/api/onboarding/${data.phone}/verify-credit`, {
    consent_for_credit_check: data.consentCreditCheck,
  });

  // Translate offer strings if not English
  let offers = result.offers || [];
  if (language !== "English" && offers.length > 0) {
    const textsToTranslate: Record<string, string> = {};
    offers.forEach((offer: any, i: number) => {
      textsToTranslate[`product_${i}`] = offer.product;
      textsToTranslate[`detail_${i}`] = offer.detail;
      textsToTranslate[`eligibility_${i}`] = offer.eligibility;
    });

    try {
      const translated = await apiCall("/api/translate/text", {
        language,
        texts: textsToTranslate,
      });
      offers = offers.map((offer: any, i: number) => ({
        ...offer,
        type: translated[`product_${i}`] ?? offer.product,
        detail: translated[`detail_${i}`] ?? offer.detail,
        eligibility: translated[`eligibility_${i}`] ?? offer.eligibility,
      }));
    } catch {
      // fallback: keep English offers
    }
  }

  updateData({
    status: result.final_status,
    riskScore: result.risk_score,
    completeness: result.completeness,
    offers,
    hasConflicts: result.has_conflicts || false,
  });
  setStep(5);
  }
    } catch (err: any) {
      setError(err.message || strings.error_generic);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setData({ ...INITIAL_DATA });
    setStep(0);
    setError(null);
    setScreen("language");
    setStrings({ ...DEFAULT_STRINGS });
    setTranslateProgress(0);
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "linear-gradient(135deg, #071410 0%, #0B1F16 50%, #060d09 100%)",
      fontFamily: "'Inter', sans-serif",
      display: "flex", alignItems: "center", justifyContent: "center", padding: "20px",
    }}>
      {/* Ambient glows */}
      <div style={{ position: "fixed", top: "-20%", left: "-10%", width: 600, height: 600, borderRadius: "50%", background: "radial-gradient(circle, rgba(11,110,79,0.18) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />
      <div style={{ position: "fixed", bottom: "-20%", right: "-10%", width: 500, height: 500, borderRadius: "50%", background: "radial-gradient(circle, rgba(124,58,237,0.12) 0%, transparent 65%)", pointerEvents: "none", zIndex: 0 }} />

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
        style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: 480, ...gl(0.06, 24), padding: "36px 28px" }}>

        {/* Logo */}
        <div className="flex items-center justify-center gap-2.5 mb-2">
          <Shield size={18} style={{ color: G_VIB }} />
          <span style={{ fontFamily: "'Anton', sans-serif", color: "#fff", fontSize: 18, letterSpacing: "0.1em" }}>VERIFARM</span>
        </div>
        <p className="text-center text-xs mb-6" style={{ color: "rgba(255,255,255,0.3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
          Farmer Verification
        </p>

        <AnimatePresence mode="wait">
          {screen === "language" ? (
            <motion.div key="language" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.3 }}>
              <LanguagePicker onSelect={handleLanguageSelect} />
            </motion.div>
          ) : (
            <motion.div key="form" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.3 }}>
              {/* Translation progress */}
              {translateProgress < 100 && <TranslatingBadge language={language} progress={translateProgress} />}

              {step < 5 && <StepIndicator steps={STEPS(strings)} current={step} />}

              <AnimatePresence mode="wait">
                <motion.div key={step} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.3 }}>
                  {step === 0 && <StepRegister data={data} onUpdate={updateData} onNext={handleNext} isLoading={isLoading} error={error} t={strings} />}
                  {step === 1 && <StepIdentity data={data} onUpdate={updateData} onNext={handleNext} onBack={() => setStep(0)} isLoading={isLoading} error={error} t={strings} />}
                  {step === 2 && <StepLand data={data} onUpdate={updateData} onNext={handleNext} onBack={() => setStep(1)} isLoading={isLoading} error={error} t={strings} />}
                  {step === 3 && <StepProduction data={data} onUpdate={updateData} onNext={handleNext} onBack={() => setStep(2)} isLoading={isLoading} error={error} t={strings} />}
                  {step === 4 && <StepCredit data={data} onUpdate={updateData} onNext={handleNext} onBack={() => setStep(3)} isLoading={isLoading} error={error} t={strings} />}
                  {step === 5 && <StepResult data={data} onReset={handleReset} onComplete={onComplete} t={strings} />}
                </motion.div>
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}