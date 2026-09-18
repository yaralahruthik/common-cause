import type { DetailMember } from "./api";

export interface TreeNode {
  lei: string;
  name: string | null;
  jurisdiction: string | null;
  role: "root" | "intermediate" | "member";
  // Levels below the Ultimate Parent, and the horizontal position in leaf slots (0 is the leftmost leaf).
  depth: number;
  x: number;
  // Portfolio members whose own record this is.
  members: DetailMember[];
  // Reached only through Matches the analyst has not confirmed.
  dashed: boolean;
}

export interface TreeEdge {
  // Child to parent: the parent consolidates the child.
  from: string;
  to: string;
  dashed: boolean;
  // The walk broke off before this hop; the registry's Declared Ultimate Parent stands in for it.
  declared: boolean;
}

export interface Tree {
  nodes: TreeNode[];
  edges: TreeEdge[];
  slots: number;
  levels: number;
}

/** Lays out every member's ownership path as one tree under their shared Ultimate Parent. Each path runs from the
 *  member's own record up to the parent, so each node is placed once however many members pass through it. */
export function layoutTree(members: DetailMember[]): Tree {
  const nodes = new Map<string, TreeNode>();
  const children = new Map<string, string[]>();
  const edges = new Map<string, TreeEdge>();
  for (const member of members) {
    member.path.forEach((step, i) => {
      const node = nodes.get(step.lei) ?? {
        lei: step.lei,
        name: step.name,
        jurisdiction: step.jurisdiction,
        role: "intermediate" as const,
        depth: 0,
        x: 0,
        members: [],
        dashed: true,
      };
      nodes.set(step.lei, node);
      if (i === 0) node.members.push(member);
      if (member.firm) node.dashed = false;
      const parent = member.path[i + 1];
      if (!parent) return;
      const key = `${step.lei}>${parent.lei}`;
      const edge = edges.get(key);
      if (edge) {
        edge.dashed &&= !member.firm;
        return;
      }
      edges.set(key, {
        from: step.lei,
        to: parent.lei,
        dashed: !member.firm,
        declared: member.basis === "declared" && i === member.path.length - 2,
      });
      children.set(parent.lei, [...(children.get(parent.lei) ?? []), step.lei]);
    });
  }
  const rootLei = members.find((m) => m.path.length)?.path.at(-1)?.lei;
  const ordered: TreeNode[] = [];
  let slots = 0;
  let levels = 0;
  const placed = new Set<string>();
  const place = (lei: string, depth: number): number => {
    const node = nodes.get(lei)!;
    // The API never repeats a company on a path; this guards the layout against a loop all the same.
    if (placed.has(lei)) return node.x;
    placed.add(lei);
    node.depth = depth;
    node.role = depth === 0 ? "root" : node.members.length ? "member" : "intermediate";
    levels = Math.max(levels, depth + 1);
    ordered.push(node);
    const below = children.get(lei) ?? [];
    node.x = below.length ? below.map((c) => place(c, depth + 1)).reduce((a, b) => a + b) / below.length : slots++;
    return node.x;
  };
  if (rootLei) place(rootLei, 0);
  const byLevel = ordered.sort((a, b) => a.depth - b.depth || a.x - b.x);
  return { nodes: byLevel, edges: [...edges.values()], slots, levels };
}
