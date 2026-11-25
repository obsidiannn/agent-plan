export type Option = {
  key: string;
  content: string;
};

export function parseOptions(json: string): Option[] {
  try {
    const value = JSON.parse(json) as unknown;
    if (!Array.isArray(value)) return [];
    return value
      .filter(
        (item): item is Option =>
          !!item &&
          typeof item === "object" &&
          typeof (item as Option).key === "string" &&
          typeof (item as Option).content === "string",
      )
      .map((item) => ({ key: item.key, content: item.content }));
  } catch {
    return [];
  }
}

export function parseAnswer(json: string | null | undefined): string[] {
  if (!json) return [];
  try {
    const value = JSON.parse(json) as unknown;
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is string => typeof item === "string");
  } catch {
    return [];
  }
}

export function stringifyAnswer(answer: string[]) {
  return JSON.stringify(answer);
}

export function formatDuration(seconds: number | null | undefined) {
  if (seconds == null || seconds < 0) return "-";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h} 小时 ${m} 分`;
  if (m > 0) return `${m} 分 ${s} 秒`;
  return `${s} 秒`;
}
