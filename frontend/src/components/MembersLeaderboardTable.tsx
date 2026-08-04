import { Table, Text } from "@mantine/core";
import { useMemo, useState, type KeyboardEvent } from "react";

import type { MembersLeaderboardRow } from "@/api/types";
import { MemberLink } from "@/components/MemberLink";
import { formatDisclosedRange } from "@/utils/format";

type SortKey =
  | "member"
  | "trades"
  | "tickers"
  | "amount_high"
  | "chamber"
  | "party"
  | "state";
type SortDir = "asc" | "desc";

type MembersLeaderboardTableProps = {
  rows: MembersLeaderboardRow[];
  selectedMember?: string;
  onSelect?: (member: string) => void;
  /** When true, member names are links to `/members?member=…` (Home). */
  linkMembers?: boolean;
  testId?: string;
};

function compareRows(
  a: MembersLeaderboardRow,
  b: MembersLeaderboardRow,
  key: SortKey,
  dir: SortDir,
): number {
  const sign = dir === "asc" ? 1 : -1;
  if (key === "trades" || key === "tickers" || key === "amount_high") {
    const av = key === "amount_high" ? a.amount_high : a[key];
    const bv = key === "amount_high" ? b.amount_high : b[key];
    return (av - bv) * sign;
  }
  const av = String(a[key] ?? "").toLowerCase();
  const bv = String(b[key] ?? "").toLowerCase();
  if (av < bv) return -1 * sign;
  if (av > bv) return 1 * sign;
  return 0;
}

type SortableThProps = {
  label: string;
  sortKey: SortKey;
  active: { key: SortKey; dir: SortDir };
  onSort: (next: { key: SortKey; dir: SortDir }) => void;
};

function SortableTh({ label, sortKey, active, onSort }: SortableThProps) {
  const isActive = active.key === sortKey;
  const indicator = !isActive ? "↕" : active.dir === "asc" ? "↑" : "↓";
  const nextDir = isActive && active.dir === "asc" ? "desc" : "asc";
  return (
    <Table.Th
      role="button"
      tabIndex={0}
      aria-sort={isActive ? (active.dir === "asc" ? "ascending" : "descending") : "none"}
      onClick={() => onSort({ key: sortKey, dir: nextDir })}
      onKeyDown={(e: KeyboardEvent<HTMLTableCellElement>) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSort({ key: sortKey, dir: nextDir });
        }
      }}
      style={{ cursor: "pointer", userSelect: "none" }}
      data-testid={`members-leaderboard-sort-${sortKey}`}
    >
      <span>
        {label} <span style={{ opacity: 0.5, fontSize: "0.85em" }}>{indicator}</span>
      </span>
    </Table.Th>
  );
}

/** Sortable, clickable per-filer leaderboard shared by Home and Members. */
export function MembersLeaderboardTable({
  rows,
  selectedMember,
  onSelect,
  linkMembers = false,
  testId = "members-leaderboard-table",
}: MembersLeaderboardTableProps) {
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "trades",
    dir: "desc",
  });

  const sorted = useMemo(
    () => [...rows].sort((a, b) => compareRows(a, b, sort.key, sort.dir)),
    [rows, sort],
  );

  if (rows.length === 0) {
    return <Text c="dimmed">No members in the current slice.</Text>;
  }

  return (
    <Table.ScrollContainer minWidth={800}>
      <Table striped highlightOnHover data-testid={testId}>
        <Table.Thead>
          <Table.Tr>
            <SortableTh label="Member" sortKey="member" active={sort} onSort={setSort} />
            <SortableTh label="Trades" sortKey="trades" active={sort} onSort={setSort} />
            <SortableTh label="Tickers" sortKey="tickers" active={sort} onSort={setSort} />
            <SortableTh
              label="Disclosed range"
              sortKey="amount_high"
              active={sort}
              onSort={setSort}
            />
            <SortableTh label="Chamber" sortKey="chamber" active={sort} onSort={setSort} />
            <SortableTh label="Party" sortKey="party" active={sort} onSort={setSort} />
            <SortableTh label="State" sortKey="state" active={sort} onSort={setSort} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sorted.map((row) => {
            const active = selectedMember === row.member;
            return (
              <Table.Tr
                key={row.member}
                style={{
                  cursor: onSelect || linkMembers ? "pointer" : "default",
                  background: active ? "var(--mantine-color-navy-0)" : undefined,
                }}
                onClick={() => onSelect?.(row.member)}
                data-testid={
                  testId === "home-leaderboard-table"
                    ? "home-leaderboard-row"
                    : "members-leaderboard-row"
                }
                data-selected={active ? "true" : undefined}
              >
                <Table.Td>
                  {linkMembers ? (
                    <MemberLink name={row.member} fw={500} />
                  ) : (
                    <Text fw={active ? 600 : 500} size="sm">
                      {row.member}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>{row.trades}</Table.Td>
                <Table.Td>{row.tickers}</Table.Td>
                <Table.Td>
                  {row.disclosed_range ??
                    formatDisclosedRange(row.amount_low, row.amount_high)}
                </Table.Td>
                <Table.Td>{row.chamber}</Table.Td>
                <Table.Td>{row.party}</Table.Td>
                <Table.Td>{row.state}</Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
