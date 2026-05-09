#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const root = process.cwd();
const srcRoot = path.join(root, "src");
const slicedLayers = new Set(["widgets", "features", "entities"]);
const layerRank = new Map([
  ["app", 5],
  ["widgets", 4],
  ["features", 3],
  ["entities", 2],
  ["shared", 1],
  ["lib", 1],
  ["i18n", 1],
  ["messages", 1],
  ["test", 1],
]);
const bannedCompatDirs = [
  "src/components",
  "src/hooks",
  "src/lib/hooks",
  "src/lib/registry",
];
const allowedAppTargets = new Set(["widgets", "shared", "lib", "i18n", "messages"]);

const violations = [];

function rel(filePath) {
  return path.relative(root, filePath).replaceAll(path.sep, "/");
}

function hasTrackedSourceFiles(dirPath) {
  if (!fs.existsSync(dirPath)) return false;
  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    const fullPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      if (hasTrackedSourceFiles(fullPath)) return true;
      continue;
    }
    if (/\.(ts|tsx|js|jsx|mjs|cjs)$/.test(entry.name)) return true;
  }
  return false;
}

function collectSourceFiles(dirPath, output = []) {
  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    const fullPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".next") continue;
      collectSourceFiles(fullPath, output);
      continue;
    }
    if (!/\.(ts|tsx)$/.test(entry.name)) continue;
    if (entry.name.includes(".test.") || entry.name.includes(".spec.")) continue;
    if (rel(fullPath).startsWith("src/test/")) continue;
    output.push(fullPath);
  }
  return output;
}

function metaFor(filePath) {
  const relative = path.relative(srcRoot, filePath).replaceAll(path.sep, "/");
  if (relative.startsWith("..")) return null;
  const parts = relative.split("/");
  const layer = parts[0];
  return {
    layer,
    rank: layerRank.get(layer),
    slice: slicedLayers.has(layer) ? parts[1] : undefined,
    relative,
  };
}

function resolveInternalImport(specifier, sourceFile) {
  if (specifier.startsWith("@/")) {
    return {
      kind: "alias",
      requestedPath: specifier.slice(2),
      absolutePath: path.join(srcRoot, specifier.slice(2)),
    };
  }
  if (specifier.startsWith(".")) {
    const absolutePath = path.resolve(path.dirname(sourceFile), specifier);
    if (!path.relative(srcRoot, absolutePath).startsWith("..")) {
      return {
        kind: "relative",
        requestedPath: path.relative(srcRoot, absolutePath).replaceAll(path.sep, "/"),
        absolutePath,
      };
    }
  }
  return null;
}

function importIsSlicePublic(specifier, target) {
  return specifier === `@/${target.layer}/${target.slice}`;
}

function report(filePath, message) {
  violations.push(`${rel(filePath)}: ${message}`);
}

function checkImport(sourceFile, source, specifier) {
  const resolved = resolveInternalImport(specifier, sourceFile);
  if (!resolved) return;
  const target = metaFor(resolved.absolutePath);
  if (!target || target.rank === undefined) return;

  if (target.layer === "app" && source.layer !== "app") {
    report(sourceFile, `must not import app layer (${specifier})`);
    return;
  }

  if (source.layer === "app" && target.layer !== "app" && !allowedAppTargets.has(target.layer)) {
    report(sourceFile, `route files may only compose widgets/shared/lib/i18n (${specifier})`);
  }

  if (source.rank !== undefined && target.rank > source.rank && source.layer !== target.layer) {
    report(sourceFile, `invalid upward dependency from ${source.layer} to ${target.layer} (${specifier})`);
  }

  if (!slicedLayers.has(target.layer) || !target.slice) return;

  const sameSlice = source.layer === target.layer && source.slice === target.slice;
  if (!sameSlice && !importIsSlicePublic(specifier, target)) {
    report(
      sourceFile,
      `cross-slice import must use public API @/${target.layer}/${target.slice} (${specifier})`,
    );
  }
}

for (const dir of bannedCompatDirs) {
  const dirPath = path.join(root, dir);
  if (hasTrackedSourceFiles(dirPath)) {
    violations.push(`${dir}: retired compatibility directory still contains source files`);
  }
}

for (const filePath of collectSourceFiles(srcRoot)) {
  const source = metaFor(filePath);
  if (!source) continue;
  const text = fs.readFileSync(filePath, "utf8");
  const kind = filePath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const ast = ts.createSourceFile(filePath, text, ts.ScriptTarget.Latest, true, kind);

  for (const statement of ast.statements) {
    if (
      (ts.isImportDeclaration(statement) || ts.isExportDeclaration(statement)) &&
      statement.moduleSpecifier &&
      ts.isStringLiteral(statement.moduleSpecifier)
    ) {
      checkImport(filePath, source, statement.moduleSpecifier.text);
    }
  }
}

if (violations.length > 0) {
  console.error("FSD boundary violations:");
  for (const violation of violations) {
    console.error(`- ${violation}`);
  }
  process.exit(1);
}

console.log("FSD boundary check passed.");
