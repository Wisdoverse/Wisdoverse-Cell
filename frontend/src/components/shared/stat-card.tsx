import { Card, CardContent } from "@/shared/ui/card";

interface StatCardProps {
  label: string;
  value: string | number;
  className?: string;
}

export function StatCard({ label, value, className }: StatCardProps) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className={`text-3xl font-bold ${className || ""}`}>{value}</div>
        <p className="text-sm text-muted-foreground mt-1">{label}</p>
      </CardContent>
    </Card>
  );
}
