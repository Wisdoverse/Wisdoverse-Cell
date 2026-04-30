"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { rejectRequirement } from "@/lib/api/feedback";

interface RejectSheetProps {
  id: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function RejectSheet({ id, onClose, onSuccess }: RejectSheetProps) {
  const t = useTranslations("requirements");
  const tc = useTranslations("common");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);

  const handleReject = async () => {
    if (!id || !reason.trim()) return;
    setLoading(true);
    try {
      await rejectRequirement(id, reason.trim(), "user");
      toast.success(t("rejectSuccess"));
      setReason("");
      onSuccess();
      onClose();
    } catch (err) {
      console.error("[reject-sheet] Failed to reject requirement:", id, err);
      toast.error(tc("error"));
    } finally {
      setLoading(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setReason("");
      onClose();
    }
  };

  return (
    <Sheet open={!!id} onOpenChange={handleOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{t("rejectTitle")}</SheetTitle>
          <SheetDescription>{t("rejectReason")}</SheetDescription>
        </SheetHeader>
        <div className="px-4 py-4">
          <Textarea
            placeholder={t("rejectReasonPlaceholder")}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={4}
          />
        </div>
        <SheetFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={loading}>
            {tc("cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={handleReject}
            disabled={loading || !reason.trim()}
          >
            {tc("reject")}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
