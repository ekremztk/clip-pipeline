"use client";

import { Check } from "lucide-react";

/**
 * The three marks an operator leaves on a clip after looking at it.
 *
 * A job card already carries a blue scalloped tick meaning "I went through
 * this". A clip needs to say more than that, because going through a clip ends
 * in one of three places: it went out, it was thrown away, or it was good
 * enough to keep but not today. So the same badge, three colours.
 */

export type ReviewMark = "unreviewed" | "maybe" | "rejected" | "posted";

export const MARK_COLORS: Record<Exclude<ReviewMark, "unreviewed">, string> = {
    posted: "#16C264",   // green — picked and published
    rejected: "#F0333B", // red — looked at, dropped
    maybe: "#1355F0",    // blue — looked at, undecided, come back to it
};

export const MARK_LABELS: Record<Exclude<ReviewMark, "unreviewed">, string> = {
    posted: "Published",
    rejected: "Rejected",
    maybe: "Not sure yet",
};

/** Order the pickers render in: the outcome you want most, first. */
export const MARK_ORDER: Exclude<ReviewMark, "unreviewed">[] = ["posted", "rejected", "maybe"];

/**
 * Scalloped verified-style disc — the same 24-point ring the job card uses, so
 * the two surfaces read as one system. Only the fill changes.
 */
export function ReviewBadge({ mark, size = 20 }: { mark: Exclude<ReviewMark, "unreviewed">; size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
            <path
                d="M12.00 0.00L14.61 2.24L18.00 1.61L19.14 4.86L22.39 6.00L21.76 9.39L24.00 12.00L21.76 14.61L22.39 18.00L19.14 19.14L18.00 22.39L14.61 21.76L12.00 24.00L9.39 21.76L6.00 22.39L4.86 19.14L1.61 18.00L2.24 14.61L0.00 12.00L2.24 9.39L1.61 6.00L4.86 4.86L6.00 1.61L9.39 2.24Z"
                fill={MARK_COLORS[mark]}
            />
            <path
                d="M6.9 12.3l3.3 3.3 6.9-6.9"
                fill="none"
                stroke="#ffffff"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
}

/**
 * Three buttons revealed on hover, matching the job card's tick control.
 * Clicking the mark a clip already carries clears it, so a mis-click costs one
 * more click rather than a trip into the clip.
 */
export function ReviewMarkPicker({
    mark,
    onPick,
}: {
    mark: ReviewMark;
    onPick: (next: ReviewMark) => void;
}) {
    return (
        <div
            className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ zIndex: 20 }}
        >
            {MARK_ORDER.map(m => (
                <button
                    key={m}
                    title={mark === m ? `Clear "${MARK_LABELS[m]}"` : MARK_LABELS[m]}
                    className="w-6 h-6 rounded-md flex items-center justify-center transition-colors"
                    style={{
                        background: "rgba(0,0,0,0.7)",
                        color: mark === m ? MARK_COLORS[m] : "#ababab",
                    }}
                    onClick={e => {
                        e.stopPropagation();
                        onPick(mark === m ? "unreviewed" : m);
                    }}
                >
                    <Check size={13} strokeWidth={3} />
                </button>
            ))}
        </div>
    );
}
