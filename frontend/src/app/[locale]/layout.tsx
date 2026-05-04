import type { Metadata } from "next";
import { getMessages } from "next-intl/server";
import { notFound } from "next/navigation";
import { routing } from "@/i18n/routing";
import { LocaleRootShell } from "@/widgets/root-shell";
import "../globals.css";

export const metadata: Metadata = {
  title: "Wisdoverse Cell",
  description: "AI Native Company OS",
};

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!(routing.locales as readonly string[]).includes(locale)) {
    notFound();
  }
  const messages = await getMessages();

  return (
    <LocaleRootShell locale={locale} messages={messages}>
      {children}
    </LocaleRootShell>
  );
}
