//
//  ContentView.swift
//  ski-tracking-tool
//
//  Created by Daniel Lutziger on 06.04.2026.
//

import SwiftUI

enum AppScreen {
    case main
    case skiType
    case rating
}

struct ContentView: View {
    @State private var store = EventStore()

    @State private var screen: AppScreen = .main
    @State private var pendingSkiType: String? = nil
    @State private var lastActivity: String? = nil
    @State private var showDataPreview = false
    @State private var showResetConfirm = false

    // Toast
    @State private var toastMessage: String? = nil
    @State private var toastColor: Color = .green

    var body: some View {
        ZStack {
            MountainBackground()

            VStack(spacing: 0) {
                topBar

                ScrollView(.vertical, showsIndicators: false) {
                    VStack(spacing: 20) {
                        Group {
                            switch screen {
                            case .main:
                                activityGrid
                                    .transition(.asymmetric(
                                        insertion: .move(edge: .leading).combined(with: .opacity),
                                        removal: .move(edge: .leading).combined(with: .opacity)
                                    ))
                            case .skiType:
                                SkiTypePicker(
                                    onSelectWithRating: { typeId in
                                        pendingSkiType = typeId
                                        withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                                            screen = .rating
                                        }
                                    },
                                    onSelectImmediate: { typeId in
                                        store.add(LabelEvent(activity: "ski", skiType: typeId))
                                        lastActivity = "ski"
                                        showToast("Run started", color: Color(red: 0.3, green: 0.85, blue: 0.5))
                                        withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                                            screen = .main
                                        }
                                    },
                                    onBack: {
                                        withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                                            screen = .main
                                        }
                                    }
                                )
                                .transition(.asymmetric(
                                    insertion: .move(edge: .trailing).combined(with: .opacity),
                                    removal: .move(edge: .trailing).combined(with: .opacity)
                                ))
                            case .rating:
                                RatingPicker(
                                    skiType: pendingSkiType,
                                    onSelect: { ratingId in
                                        store.add(LabelEvent(
                                            activity: "ski",
                                            skiType: pendingSkiType,
                                            rating: ratingId
                                        ))
                                        lastActivity = "ski"
                                        let label = pendingSkiType.map { skiTypeLabel($0) } ?? "Ski"
                                        let emoji = ratings[ratingId].emoji
                                        showToast("\(label) \(emoji)", color: .red)
                                        pendingSkiType = nil
                                        withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                                            screen = .main
                                        }
                                    },
                                    onBack: {
                                        withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                                            screen = .skiType
                                        }
                                    }
                                )
                                .transition(.asymmetric(
                                    insertion: .move(edge: .trailing).combined(with: .opacity),
                                    removal: .move(edge: .trailing).combined(with: .opacity)
                                ))
                            }
                        }
                        .animation(.spring(response: 0.35, dampingFraction: 0.8), value: screen)

                        EventTimeline(events: store.events)
                    }
                    .padding(.top, 8)
                }
            }

            // Toast overlay
            VStack {
                if let message = toastMessage {
                    ConfirmationToast(message: message, color: toastColor)
                        .transition(.move(edge: .top).combined(with: .opacity))
                        .padding(.top, 60)
                }
                Spacer()
            }
            .zIndex(100)
        }
        .preferredColorScheme(.dark)
        .sheet(isPresented: $showDataPreview) {
            DataPreviewView(store: store)
                .preferredColorScheme(.dark)
        }
        .alert("Clear all events?", isPresented: $showResetConfirm) {
            Button("Cancel", role: .cancel) {}
            Button("Clear", role: .destructive) {
                store.clearAll()
                lastActivity = nil
            }
        } message: {
            Text("This will delete all \(store.events.count) logged events.")
        }
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Ski Tracker")
                    .font(.system(size: 24, weight: .bold))
                    .foregroundColor(.white)
                Text("\(store.events.count) events")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.white.opacity(0.35))
            }

            Spacer()

            Button(action: { showDataPreview = true }) {
                Image(systemName: "chart.bar.xaxis")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(.white.opacity(0.5))
                    .frame(width: 40, height: 40)
                    .background(Circle().fill(Color.white.opacity(0.06)))
            }
            .disabled(store.events.isEmpty)
            .opacity(store.events.isEmpty ? 0.3 : 1)

            Menu {
                Button(role: .destructive, action: { showResetConfirm = true }) {
                    Label("Clear all events", systemImage: "trash")
                }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(.white.opacity(0.5))
                    .frame(width: 40, height: 40)
                    .background(Circle().fill(Color.white.opacity(0.06)))
            }
        }
        .padding(.horizontal)
        .padding(.top, 12)
        .padding(.bottom, 8)
    }

    // MARK: - Activity Grid

    private var activityGrid: some View {
        VStack(spacing: 14) {
            SectionHeader(title: "Activity", icon: "figure.run")

            LazyVGrid(columns: [
                GridItem(.flexible(), spacing: 10),
                GridItem(.flexible(), spacing: 10),
                GridItem(.flexible(), spacing: 10)
            ], spacing: 10) {
                ForEach(activities) { activity in
                    ActivityButton(
                        activity: activity,
                        isLast: lastActivity == activity.id
                    ) {
                        if activity.id == "ski" {
                            withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                                screen = .skiType
                            }
                        } else {
                            store.add(LabelEvent(activity: activity.id))
                            lastActivity = activity.id
                            showToast(activity.label, color: activity.color)
                        }
                    }
                }
            }
        }
        .padding(.horizontal)
    }

    // MARK: - Toast

    private func showToast(_ message: String, color: Color) {
        withAnimation(.spring(response: 0.4, dampingFraction: 0.75)) {
            toastMessage = message
            toastColor = color
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
            withAnimation(.easeOut(duration: 0.3)) {
                toastMessage = nil
            }
        }
    }
}

#Preview {
    ContentView()
}
