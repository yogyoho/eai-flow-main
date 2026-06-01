// Patch prosemirror-model's renderSpec to handle DOM element nodes.
// BlockNote's toDOM returns DOM elements, but prosemirror-model's _renderSpec
// only handles text nodes (nodeType==3). This patch makes it handle any nodeType.
import { DOMSerializer } from "@tiptap/pm/model";

type RenderSpecResult = { dom: Node; contentDOM?: Node };
type RenderSpecFn = (
  doc: Document,
  structure: unknown,
  xmlNS?: string | null,
  blockArraysIn?: Record<string, unknown>,
) => RenderSpecResult;

const serializer = DOMSerializer as unknown as { renderSpec: RenderSpecFn };
const origRenderSpec = serializer.renderSpec;
serializer.renderSpec = function (
  doc: Document,
  structure: unknown,
  xmlNS?: string | null,
  blockArraysIn?: Record<string, unknown>,
): RenderSpecResult {
  // Handle DOM element nodes (BlockNote's render functions return these)
  if (
    structure != null &&
    typeof structure === "object" &&
    "nodeType" in (structure as object) &&
    (structure as { nodeType: number }).nodeType != null
  ) {
    return { dom: structure as Node };
  }
  // Handle objects with a .dom property that's a DOM node
  if (
    structure != null &&
    typeof structure === "object" &&
    "dom" in (structure as object) &&
    (structure as { dom: unknown }).dom != null &&
    typeof (structure as { dom: unknown }).dom === "object" &&
    "nodeType" in (structure as { dom: object }).dom
  ) {
    return structure as { dom: Node; contentDOM?: Node };
  }
  return origRenderSpec.call(DOMSerializer, doc, structure, xmlNS ?? null, blockArraysIn);
};

export {};
