import { readFileSync } from "node:fs";

// Full sanitizer AS IN mathMarkdown.ts (all steps, exact order)
function sanitize(md) {
  if (!md) return md;
  let s = md;
  // 1) math \\X → \X
  const deDouble = (body) => body.replace(/\\{2,}([a-zA-Z])/g, "\\$1");
  s = s.replace(/\$\$([\s\S]+?)\$\$/g, (_m, body) => "$$" + deDouble(body) + "$$");
  s = s.replace(/\$([^\$\n]+?)\$/g, (_m, body) => "$" + deDouble(body) + "$");
  // 2) block-math newline after
  s = s.replace(/(\$\$[\s\S]+?\$\$)\\{0,2}(?=[^\n\r])/g, "$1\n");
  // 3) over-escaped bold/headings
  s = s.replace(/\\{2,}\*/g, "*");
  s = s.replace(/\\{2,}#/g, "#");
  // 4) \~ → ~
  s = s.replace(/\\~/g, "~");
  // 5) table :: colon fix
  s = s.replace(/\|:{2,}/g, "|:").replace(/:{2,}\|/g, ":|");
  // 6) over-escaped blockquote
  s = s.replace(/\\{2,}> /g, "> ");
  // 7a) $$&gt;...$$ → > ...
  s = s.replace(/\$\$&gt;([\s\S]*?)\$\$/g, (_m, content) => "\n> " + content.replace(/\\\*/g, "*") + "\n");
  s = s.replace(/\$\$>([\s\S]*?)\$\$/g, (_m, content) => "\n> " + content.replace(/\\\*/g, "*") + "\n");
  // 7b) $$&gt; line-no-close → >
  s = s.replace(/^\$\$&gt;([^\n]+)/gm, (_m, content) => "> " + content.replace(/\\\*/g, "*").replace(/\\{2,}\*/g, "*"));
  return s;
}

const F = process.argv[2];
const orig = readFileSync(F, "utf8");
const clean = sanitize(orig);

// Find the 96.4 / 夏季蒸发 area in orig and clean
const oLines = orig.split("\n");
const cLines = clean.split("\n");
const oIdx = oLines.findIndex(l => l.includes("夏季蒸发损失"));
const cIdx = cLines.findIndex(l => l.includes("夏季蒸发损失"));

console.log("=== ORIG line ===", "L" + (oIdx + 1), "(starts with $$&gt;)", oIdx >= 0 && oLines[oIdx].startsWith("$$&gt;"));
if (oIdx >= 0) console.log(oLines[oIdx].slice(0, 200));
console.log("=== CLEANED line ===", cIdx >= 0 ? "L" + (cIdx + 1) : "NOT FOUND", "(starts with > )", cIdx >= 0 && cLines[cIdx].startsWith("> "));
if (cIdx >= 0) console.log(cLines[cIdx].slice(0, 200));

// Also show step-by-step: what does EACH step do to L226
console.log("\n=== STEP-BY-STEP on L226 ===");
let s = oLines[oIdx];
console.log("RAW:", JSON.stringify(s).slice(0, 180));
// step 1 would match block $$ that closes with $$; L226 has no close -> skip
// step 3: over-escaped bold
let after3 = s.replace(/\\{2,}\*/g, "*");
console.log("after step3 (\\\\{2,}\\*):", JSON.stringify(after3).slice(0, 160));
// step 7b: $$&gt; line with no close
let after7b = after3.replace(/^\$\$&gt;([^\n]+)/gm, (_m, content) => "> " + content.replace(/\\\*/g, "*").replace(/\\{2,}\*/g, "*"));
console.log("after step7b:", JSON.stringify(after7b).slice(0, 160));
