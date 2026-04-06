//
//  TimelineView.swift
//  ski-tracking-tool
//
//  Created by Daniel Lutziger on 06.04.2026.
//

import SwiftUI

struct EventTimeline: View {
    let events: [LabelEvent]

    var body: some View {
        VStack(spacing: 12) {
            SectionHeader(title: "Timeline", icon: "clock")

            if events.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "snowflake")
                        .font(.system(size: 32, weight: .light))
                        .foregroundColor(.white.opacity(0.15))
                    Text("No events yet")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(.white.opacity(0.3))
                }
                .frame(maxWidth: .infinity)
                .frame(height: 120)
                .glassCard()
            } else {
                VStack(spacing: 2) {
                    ForEach(Array(events.reversed().enumerated()), id: \.element.id) { index, event in
                        EventRow(event: event, index: index)
                    }
                }
                .glassCard(padding: 8)
            }
        }
        .padding(.horizontal)
        .padding(.bottom, 20)
    }
}

struct EventRow: View {
    let event: LabelEvent
    let index: Int

    @State private var appeared = false

    var body: some View {
        HStack(spacing: 12) {
            // Colored dot
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)

            // Icon
            Image(systemName: icon)
                .foregroundColor(color)
                .font(.system(size: 14, weight: .medium))
                .frame(width: 20)

            // Name + rating
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(displayName(for: event))
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(color)

                    if let r = event.rating, r < ratings.count {
                        Text(ratings[r].emoji)
                            .font(.system(size: 12))
                    }
                }
                Text(event.timestamp, style: .time)
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.3))
            }

            Spacer()

            if let r = event.rating, r < ratings.count {
                Text(ratings[r].label)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(ratings[r].color.opacity(0.7))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(
                        Capsule().fill(ratings[r].color.opacity(0.1))
                    )
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .opacity(appeared ? 1 : 0)
        .offset(x: appeared ? 0 : -20)
        .animation(
            .spring(response: 0.4, dampingFraction: 0.8).delay(min(Double(index) * 0.03, 0.25)),
            value: appeared
        )
        .onAppear { appeared = true }
    }

    private var color: Color {
        activityFor(event.activity)?.color ?? .white
    }

    private var icon: String {
        activityFor(event.activity)?.icon ?? "questionmark"
    }
}
