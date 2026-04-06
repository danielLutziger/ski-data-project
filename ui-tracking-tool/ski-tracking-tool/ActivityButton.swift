//
//  ActivityButton.swift
//  ski-tracking-tool
//
//  Created by Daniel Lutziger on 06.04.2026.
//

import SwiftUI

struct ActivityButton: View {
    let activity: Activity
    let isLast: Bool
    let action: () -> Void

    @State private var isPressed = false

    var body: some View {
        Button(action: {
            let g = UIImpactFeedbackGenerator(style: .medium)
            g.impactOccurred()
            action()
        }) {
            VStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(activity.color.opacity(isLast ? 0.3 : 0.12))
                        .frame(width: 44, height: 44)
                    Image(systemName: activity.icon)
                        .font(.system(size: 20, weight: .medium))
                        .foregroundColor(isLast ? .white : activity.color)
                }

                Text(activity.label)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(isLast ? .white : .white.opacity(0.7))
            }
            .frame(maxWidth: .infinity)
            .frame(height: 100)
            .background(
                RoundedRectangle(cornerRadius: 18)
                    .fill(
                        isLast
                            ? activity.color.opacity(0.2)
                            : Color.white.opacity(0.04)
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18)
                    .stroke(
                        isLast ? activity.color.opacity(0.5) : Color.white.opacity(0.06),
                        lineWidth: isLast ? 1.5 : 0.5
                    )
            )
            .scaleEffect(isPressed ? 0.92 : 1.0)
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
