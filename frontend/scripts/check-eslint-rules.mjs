import assert from "node:assert/strict";
import { ESLint } from "eslint";

const eslint = new ESLint();
const cases = [
  ["react/display-name", "export default () => <div />;"],
  ["import/no-anonymous-default-export", "export default { value: 1 };"],
  ["jsx-a11y/alt-text", 'export default function Probe() { return <img src="/photo.png" />; }'],
  ["@next/next/no-img-element", 'export default function Probe() { return <img alt="Photo" src="/photo.png" />; }'],
  ["@typescript-eslint/no-explicit-any", 'export const value: any = "x";'],
  ["react-hooks/rules-of-hooks", 'import { useState } from "react"; export function Probe({ enabled }: { enabled: boolean }) { if (enabled) useState(0); return null; }'],
  ["react-hooks/set-state-in-effect", 'import { useEffect, useState } from "react"; export function Probe() { const [value, setValue] = useState(0); useEffect(() => { setValue(1); }, []); return <div>{value}</div>; }'],
];

for (const [ruleId, code] of cases) {
  const [result] = await eslint.lintText(code, { filePath: "src/app/eslint-rule-probe.tsx" });
  assert(result.messages.some((message) => message.ruleId === ruleId), `${ruleId} did not report the invalid code`);
}

console.log(`ESLint rule checks passed (${cases.length} rules).`);
