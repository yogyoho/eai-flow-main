import { Badge, type BadgeProps } from "@/components/ui/badge";

const TONE_VARIANT: Record<string, BadgeProps["variant"]> = {
  emerald: "success",
  amber: "warning",
  rose: "danger",
  blue: "info",
  sky: "info",
  slate: "slate",
  violet: "purple",
};

export function StatusBadge({
  tone,
  label,
  dot = true,
  className,
}: {
  tone?: string | null;
  label: string;
  dot?: boolean;
  className?: string;
}) {
  const variant = TONE_VARIANT[tone || "slate"] || "slate";
  return (
    <Badge variant={variant} className={className}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />}
      {label}
    </Badge>
  );
}

export function PublishBadge({ value }: { value: number }) {
  if (value === 1) return <Badge variant="success">已发布</Badge>;
  if (value === 9) return <Badge variant="slate">已失效</Badge>;
  return <Badge variant="outline">未发布</Badge>;
}
