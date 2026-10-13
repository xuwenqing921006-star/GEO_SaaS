import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

const outputDirectory = join(
  process.cwd(),
  "node_modules",
  ".t002-production-build",
);
const forbiddenStrings = [
  "mock-csrf-token",
  "莱恩美术",
  "演示数据",
  "演示解析任务完成",
  "演示诊断任务已受理",
  "当前客户已确认名称",
  "当前客户已确认服务",
  "生成优化版本",
  "优化版本待确认",
  "草稿已保存为独立手工版本",
];

const collectFiles = async (directory) => {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const path = join(directory, entry.name);
      return entry.isDirectory() ? collectFiles(path) : [path];
    }),
  );
  return nested.flat();
};

const files = await collectFiles(outputDirectory);
const bundle = (
  await Promise.all(files.map((file) => readFile(file, "utf8")))
).join("\n");
const leaked = forbiddenStrings.filter((value) => bundle.includes(value));

if (leaked.length) {
  throw new Error(
    `Production bundle contains Mock-only values: ${leaked.join(", ")}`,
  );
}
