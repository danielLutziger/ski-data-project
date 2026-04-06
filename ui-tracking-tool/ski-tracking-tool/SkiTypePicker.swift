//
//  SkiTypePicker.swift
//  ski-tracking-tool
//
//  Created by Daniel Lutziger on 06.04.2026.
//

import SwiftUI

struct SkiTypePicker: View {
    let onSelectWithRating: (String) -> Void   // needs rating next
    let onSelectImmediate: (String) -> Void     // logs immediately (start run)
    let onBack: () -> Void

    @State private var appeared = false

    var body: some View {
        VStack(spacing: 14) {
            // Header
            HStack {
                Button(action: onBack) {
                    HStack(spacing: 4) {
                        Image(systemName: "chevron.left")
                            .font(.system(size: 14, weight: .semibold))
                        Text("Back")
                            .font(.system(size: 14, weight: .medium))
                    }
                    .foregroundColor(.white.opacity(0.6))
                }
                Spacer()
            }

            Text("Type of skiing")
                .font(.system(size: 22, weight: .bold))
                .foregroundColor(.white)
                .frame(maxWidth: .infinity, alignment: .leading)

            // Start run button — prominent, full width
            let startType = skiTypes.first { $0.id == "start" }!
            SkiTypeCard(skiType: startType, prominent: true) {
                onSelectImmediate(startType.id)
            }
            .opacity(appeared ? 1 : 0)
            .offset(y: appeared ? 0 : 24)
            .animation(
                .spring(response: 0.45, dampingFraction: 0.75),
                value: appeared
            )

            // Divider
            HStack(spacing: 8) {
                Rectangle()
                    .fill(Color.white.opacity(0.08))
                    .frame(height: 0.5)
                Text("after run")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.white.opacity(0.25))
                    .textCase(.uppercase)
                    .tracking(1)
                Rectangle()
                    .fill(Color.white.opacity(0.08))
                    .frame(height: 0.5)
            }
            .padding(.vertical, 4)

            // Rating-required types
            LazyVGrid(columns: [
                GridItem(.flexible(), spacing: 10),
                GridItem(.flexible(), spacing: 10)
            ], spacing: 10) {
                ForEach(Array(skiTypes.filter { $0.needsRating }.enumerated()), id: \.element.id) { index, skiType in
                    SkiTypeCard(skiType: skiType, prominent: false) {
                        onSelectWithRating(skiType.id)
                    }
                    .opacity(appeared ? 1 : 0)
                    .offset(y: appeared ? 0 : 24)
                    .animation(
                        .spring(response: 0.45, dampingFraction: 0.75).delay(Double(index) * 0.06 + 0.1),
                        value: appeared
                    )
                }
            }
        }
        .padding(.horizontal)
        .padding(.top, 8)
        .padding(.bottom, 16)
        .onAppear { appeared = true }
        .onDisappear { appeared = false }
    }
}

struct SkiTypeCard: View {
    let skiType: SkiType
    let prominent: Bool
    let action: () -> Void

    @State private var isPressed = false

    var body: some View {
        Button(action: {
            let g = UIImpactFeedbackGenerator(style: prominent ? .medium : .light)
            g.impactOccurred()
            action()
        }) {
            HStack(spacing: 10) {
                Image(systemName: skiType.icon)
                    .font(.system(size: prominent ? 18 : 16, weight: .medium))
                    .foregroundColor(
                        prominent
                            ? Color(red: 0.3, green: 0.85, blue: 0.5)
                            : Color(red: 0.95, green: 0.35, blue: 0.3)
                    )
                    .frame(width: 24)
                Text(skiType.label)
                    .font(.system(size: prominent ? 16 : 14, weight: .semibold))
                    .foregroundColor(.white.opacity(prominent ? 0.95 : 0.85))
                Spacer()
                if prominent {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white.opacity(0.3))
                }
            }
            .padding(.horizontal, 16)
            .frame(height: prominent ? 58 : 54)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(
                        prominent
                            ? Color(red: 0.3, green: 0.85, blue: 0.5).opacity(0.1)
                            : Color.white.opacity(0.06)
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(
                        prominent
                            ? Color(red: 0.3, green: 0.85, blue: 0.5).opacity(0.25)
                            : Color(red: 0.95, green: 0.3, blue: 0.25).opacity(0.15),
                        lineWidth: 0.5
                    )
            )
            .scaleEffect(isPressed ? 0.95 : 1.0)
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
