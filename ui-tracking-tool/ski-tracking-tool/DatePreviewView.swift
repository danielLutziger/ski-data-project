//
//  DatePreviewView.swift
//  ski-tracking-tool
//
//  Created by Daniel Lutziger on 06.04.2026.
//

import SwiftUI

struct DataPreviewView: View {
    var store: EventStore
    @Environment(\.dismiss) var dismiss
    @State private var showShareSheet = false
    @State private var shareItems: [Any] = []
    @State private var appeared = false

    var body: some View {
        ZStack {
            MountainBackground()

            ScrollView {
                VStack(spacing: 20) {
                    // Header
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Session data")
                                .font(.system(size: 28, weight: .bold))
                                .foregroundColor(.white)
                            Text(store.sessionDate)
                                .font(.system(size: 14))
                                .foregroundColor(.white.opacity(0.45))
                        }
                        Spacer()
                        Button(action: { dismiss() }) {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 28))
                                .foregroundColor(.white.opacity(0.3))
                        }
                    }
                    .padding(.horizontal)
                    .padding(.top, 16)

                    // Stats
                    statsSection
                        .opacity(appeared ? 1 : 0)
                        .offset(y: appeared ? 0 : 20)
                        .animation(.spring(response: 0.5, dampingFraction: 0.8).delay(0.1), value: appeared)

                    // Rating distribution
                    if store.averageRating != nil {
                        ratingSection
                            .opacity(appeared ? 1 : 0)
                            .offset(y: appeared ? 0 : 20)
                            .animation(.spring(response: 0.5, dampingFraction: 0.8).delay(0.2), value: appeared)
                    }

                    // Recent events
                    recentSection
                        .opacity(appeared ? 1 : 0)
                        .offset(y: appeared ? 0 : 20)
                        .animation(.spring(response: 0.5, dampingFraction: 0.8).delay(0.3), value: appeared)

                    // Export
                    exportSection
                        .opacity(appeared ? 1 : 0)
                        .offset(y: appeared ? 0 : 20)
                        .animation(.spring(response: 0.5, dampingFraction: 0.8).delay(0.4), value: appeared)

                    Spacer(minLength: 40)
                }
            }
        }
        .sheet(isPresented: $showShareSheet) {
            ShareSheet(items: shareItems)
        }
        .onAppear { appeared = true }
    }

    // MARK: - Stats

    private var statsSection: some View {
        VStack(spacing: 10) {
            SectionHeader(title: "Overview", icon: "chart.bar")

            LazyVGrid(columns: [
                GridItem(.flexible(), spacing: 10),
                GridItem(.flexible(), spacing: 10),
                GridItem(.flexible(), spacing: 10)
            ], spacing: 10) {
                StatCard(label: "Events", value: "\(store.events.count)", color: .blue)
                StatCard(label: "Ski runs", value: "\(store.skiEventCount)", color: .red)
                StatCard(
                    label: "Avg rating",
                    value: store.averageRating.map { String(format: "%.1f", $0) } ?? "—",
                    color: .green
                )
            }

            HStack(spacing: 10) {
                ForEach(activities) { act in
                    let count = store.countFor(act.id)
                    if count > 0 {
                        HStack(spacing: 4) {
                            Circle().fill(act.color).frame(width: 6, height: 6)
                            Text("\(count)")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundColor(.white.opacity(0.8))
                            Text(act.label)
                                .font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.4))
                        }
                    }
                }
            }
            .padding(.horizontal, 4)
            .padding(.top, 4)
        }
        .padding(.horizontal)
    }

    // MARK: - Rating Distribution

    private var ratingSection: some View {
        VStack(spacing: 10) {
            SectionHeader(title: "Rating distribution", icon: "star")

            let dist = store.ratingDistribution()
            let maxCount = dist.values.max() ?? 1

            VStack(spacing: 6) {
                ForEach(ratings) { rating in
                    let count = dist[rating.id] ?? 0
                    HStack(spacing: 10) {
                        Text(rating.emoji)
                            .font(.system(size: 16))
                            .frame(width: 24)
                        Text(rating.label)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white.opacity(0.6))
                            .frame(width: 65, alignment: .leading)
                        GeometryReader { geo in
                            RoundedRectangle(cornerRadius: 4)
                                .fill(rating.color.opacity(0.4))
                                .frame(width: max(CGFloat(count) / CGFloat(maxCount) * geo.size.width, count > 0 ? 4 : 0))
                        }
                        .frame(height: 16)
                        Text("\(count)")
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .foregroundColor(.white.opacity(0.5))
                            .frame(width: 24, alignment: .trailing)
                    }
                }
            }
            .glassCard(padding: 14)
        }
        .padding(.horizontal)
    }

    // MARK: - Recent Events

    private var recentSection: some View {
        VStack(spacing: 10) {
            SectionHeader(title: "Recent events", icon: "list.bullet")

            VStack(spacing: 0) {
                ForEach(store.events.suffix(10).reversed()) { event in
                    HStack(spacing: 10) {
                        Image(systemName: activityFor(event.activity)?.icon ?? "questionmark")
                            .foregroundColor(activityFor(event.activity)?.color ?? .white)
                            .font(.system(size: 13))
                            .frame(width: 20)
                        Text(displayName(for: event))
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(.white.opacity(0.75))
                        Spacer()
                        if let r = event.rating, r < ratings.count {
                            Text(ratings[r].emoji)
                                .font(.system(size: 13))
                        }
                        Text(event.timestamp, style: .time)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(.white.opacity(0.3))
                    }
                    .padding(.vertical, 7)
                    .padding(.horizontal, 4)
                }
            }
            .glassCard(padding: 12)
        }
        .padding(.horizontal)
    }

    // MARK: - Export

    private var exportSection: some View {
        VStack(spacing: 10) {
            SectionHeader(title: "Export", icon: "square.and.arrow.up")

            HStack(spacing: 12) {
                ExportButton(label: "CSV", icon: "doc.text", color: .blue) {
                    shareItems = [store.csvFileURL()]
                    showShareSheet = true
                }
                ExportButton(label: "JSON", icon: "curlybraces", color: .purple) {
                    shareItems = [store.jsonFileURL()]
                    showShareSheet = true
                }
                ExportButton(label: "Email", icon: "envelope", color: .orange) {
                    let body = "Ski session data from \(store.sessionDate)\n\n\(store.events.count) events logged.\n\nSee attached CSV."
                    shareItems = [body, store.csvFileURL()]
                    showShareSheet = true
                }
            }
        }
        .padding(.horizontal)
    }
}

// MARK: - Subcomponents

struct StatCard: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        VStack(spacing: 6) {
            Text(value)
                .font(.system(size: 24, weight: .bold, design: .rounded))
                .foregroundColor(.white)
            Text(label)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.white.opacity(0.4))
        }
        .frame(maxWidth: .infinity)
        .frame(height: 75)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(color.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(color.opacity(0.15), lineWidth: 0.5)
        )
    }
}

struct ExportButton: View {
    let label: String
    let icon: String
    let color: Color
    let action: () -> Void

    @State private var isPressed = false

    var body: some View {
        Button(action: {
            let g = UIImpactFeedbackGenerator(style: .light)
            g.impactOccurred()
            action()
        }) {
            VStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 20, weight: .medium))
                    .foregroundColor(color)
                Text(label)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.white.opacity(0.7))
            }
            .frame(maxWidth: .infinity)
            .frame(height: 70)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color.white.opacity(0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(color.opacity(0.2), lineWidth: 0.5)
            )
            .scaleEffect(isPressed ? 0.93 : 1.0)
            .animation(.spring(response: 0.25, dampingFraction: 0.6), value: isPressed)
        }
        .buttonStyle(.plain)
        .simultaneousGesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in isPressed = true }
                .onEnded { _ in isPressed = false }
        )
    }
}
