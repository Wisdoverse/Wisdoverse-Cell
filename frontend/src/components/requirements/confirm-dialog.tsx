"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { confirmRequirement } from "@/lib/api/feedback";

interface ConfirmDialogProps {
  id: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function ConfirmDialog({ id, onClose, onSuccess }: ConfirmDialogProps) {
  const t = useTranslations("requirements");
  const tc = useTranslations("common");
  const [loading, setLoading] = useState(false);

  const handleConfirm = async () => {
    if (!id) return;
    setLoading(true);
    try {
      await confirmRequirement(id, "user");
      toast.success(t("confirmSuccess"));
      onSuccess();
      onClose();
    } catch (err) {
      console.error("[confirm-dialog] Failed to confirm requirement:", id, err);
      toast.error(tc("error"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={!!id} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("confirmTitle")}</DialogTitle>
          <DialogDescription>{t("confirmMessage")}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {tc("cancel")}
          </Button>
          <Button onClick={handleConfirm} disabled={loading}>
            {tc("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
