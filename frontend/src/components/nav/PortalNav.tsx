"use client";

// Shared top nav so all three portals (lender dashboard, cooperative
// onboarding, partner portal) are reachable from one another. Deliberately
// framework-minimal (no Shadcn NavigationMenu primitive exists in this repo
// yet — see src/components/ui, which is empty) so this works without new
// dependencies.
import Link from "next/link";

const LINKS = [
  { href: "/", label: "Farmer Search" },
  { href: "/cooperative/onboard", label: "Cooperative Onboarding" },
  { href: "/partner", label: "Partner Portal" },
  { href: "/analytics", label: "Analytics" },
];

export function PortalNav() {
  return (
    <nav className="mb-6 flex flex-wrap gap-2 border-b border-white/10 pb-4">
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="rounded-full border border-white/15 px-3 py-1 text-xs font-medium text-white/60 transition hover:border-primary hover:text-primary"
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}

export default PortalNav;
