import type { AnchorHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

import { CitationLink, extractReactNodeText } from "./citation-link";

function isExternalUrl(href: string | undefined): boolean {
  return !!href && /^https?:\/\//.test(href);
}

/** Link renderer for artifact markdown: citation: prefix → CitationLink, otherwise underlined text. */
export function ArtifactLink(props: AnchorHTMLAttributes<HTMLAnchorElement>) {
  const childrenText = extractReactNodeText(props.children);
  if (childrenText !== null) {
    const match = /^citation:(.+)$/.exec(childrenText);
    if (match) {
      const [, text] = match;
      return <CitationLink {...props}>{text}</CitationLink>;
    }
  }
  const { className, target, rel, ...rest } = props;
  const external = isExternalUrl(props.href);
  return (
    <a
      {...rest}
      className={cn(
        "text-primary decoration-primary/30 hover:decoration-primary/60 underline underline-offset-2 transition-colors",
        className,
      )}
      target={target ?? (external ? "_blank" : undefined)}
      rel={rel ?? (external ? "noopener noreferrer" : undefined)}
    />
  );
}
