import { useMemo } from "react";
import { usePrefs } from "./prefs";

/** Theme colours as concrete strings for the charts (read from the CSS tokens). */
export function useColors() {
  const { dark } = usePrefs();
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement);
    const triplet = (name: string) => css.getPropertyValue(`--${name}`).trim().replace(/\s+/g, ", ");
    const rgb = (name: string, a?: number) => (a == null ? `rgb(${triplet(name)})` : `rgba(${triplet(name)}, ${a})`);
    return {
      pen: rgb("pen"), good: rgb("good"), bad: rgb("bad"), warn: rgb("warn"), ink: rgb("ink"), muted: rgb("muted"),
      faint: rgb("faint"), rule: rgb("rule"), sheet: rgb("sheet"), penSoft: rgb("pen", 0.15),
      axis: { stroke: rgb("faint"), fontSize: 12 },
      tooltip: { contentStyle: { background: rgb("sheet"), border: `1px solid ${rgb("rule")}`, borderRadius: 8, fontSize: 13,
        color: rgb("ink") }, labelStyle: { color: rgb("muted") } },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dark]);
}
