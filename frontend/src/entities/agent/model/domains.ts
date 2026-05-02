import type { AgentDomain } from "./types";

export interface DomainConfig {
  id: AgentDomain;
  label: string;
  color: string;
  colorLight: string;
  cssVar: string;
  icon: string;
}

export const DOMAINS: Record<AgentDomain, DomainConfig> = {
  product: {
    id: "product",
    label: "Product",
    color: "#8B5CF6",
    colorLight: "var(--domain-product-light)",
    cssVar: "--domain-product",
    icon: "Package",
  },
  engineering: {
    id: "engineering",
    label: "Engineering",
    color: "#3B82F6",
    colorLight: "var(--domain-engineering-light)",
    cssVar: "--domain-engineering",
    icon: "Code",
  },
  quality: {
    id: "quality",
    label: "Quality",
    color: "#22C55E",
    colorLight: "var(--domain-quality-light)",
    cssVar: "--domain-quality",
    icon: "ShieldCheck",
  },
  operations: {
    id: "operations",
    label: "Operations",
    color: "#F59E0B",
    colorLight: "var(--domain-operations-light)",
    cssVar: "--domain-operations",
    icon: "Server",
  },
  business: {
    id: "business",
    label: "Business",
    color: "#EC4899",
    colorLight: "var(--domain-business-light)",
    cssVar: "--domain-business",
    icon: "Briefcase",
  },
  "market-sales": {
    id: "market-sales",
    label: "Market & Sales",
    color: "#F97316",
    colorLight: "var(--domain-market-sales-light)",
    cssVar: "--domain-market-sales",
    icon: "TrendingUp",
  },
  "data-ai": {
    id: "data-ai",
    label: "Data & AI",
    color: "#06B6D4",
    colorLight: "var(--domain-data-ai-light)",
    cssVar: "--domain-data-ai",
    icon: "Brain",
  },
};

export function getDomainConfig(domain: AgentDomain): DomainConfig {
  const config = DOMAINS[domain];
  if (!config) throw new Error(`Unknown domain: ${domain}`);
  return config;
}

export const DOMAIN_LIST = Object.values(DOMAINS);
