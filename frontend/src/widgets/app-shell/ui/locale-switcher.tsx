"use client";

import { useLocale } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { locales } from "@/i18n/config";

const localeLabels: Record<string, string> = {
  zh: "中文",
  en: "English",
  ja: "日本語",
};

export function LocaleSwitcher() {
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  function onLocaleChange(newLocale: string) {
    // Replace the locale prefix in the current path
    const segments = pathname.split("/");
    segments[1] = newLocale;
    router.push(segments.join("/"));
  }

  return (
    <Select value={locale} onValueChange={onLocaleChange}>
      <SelectTrigger className="w-[100px]" size="sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {locales.map((loc) => (
          <SelectItem key={loc} value={loc}>
            {localeLabels[loc]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
