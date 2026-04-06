//
//  RatingPicker.swift
//  ski-tracking-tool
//
//  Created by Daniel Lutziger on 06.04.2026.
//

import SwiftUI

struct RatingPicker: View {
    let skiType: String?
    let onSelect: (Int) -> Void
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

            VStack(alignment: .leading, spacing: 4) {
                Text("How did it feel?")
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(.white)
                if let st = skiType {
                    Text("Ski · \(skiTypeLabel(st))")
                        .font(.system(size: 14))
                        .foregroundColor(.white.opacity(0.45))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Rating grid
            LazyVGrid(columns: [
                GridItem(.flexible(), spacing: 10),
                GridItem(.flexible(), spacing: 10),
                GridItem(.flexible(), spacing: 10)
            ], spacing: 10) {
                ForEach(Array(ratings.enumerated()), id: \.element.id) { index, rating in
                    RatingCard(rating: rating) {
                        onSelect(rating.id)
                    }
                    .opacity(appeared ? 1 : 0)
                    .scaleEffect(appeared ? 1.0 : 0.5)
                    .animation(
                        .spring(response: 0.5, dampingFraction: 0.65).delay(Double(index) * 0.06),
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

struct RatingCard: View {
    let rating: Rating
    let action: () -> Void

    @State private var isPressed = false

    var body: some View {
        Button(action: {
            let g = UINotificationFeedbackGenerator()
            g.notificationOccurred(rating.id >= 4 ? .success : rating.id <= 1 ? .error : .warning)
            action()
        }) {
            VStack(spacing: 8) {
                Text(rating.emoji)
                    .font(.system(size: 28))
                Text(rating.label)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.white.opacity(0.7))
            }
            .frame(maxWidth: .infinity)
            .frame(height: 80)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(rating.color.opacity(0.1))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(rating.color.opacity(0.2), lineWidth: 0.5)
            )
            .scaleEffect(isPressed ? 0.88 : 1.0)
            .animation(.spring(response: 0.2, dampingFraction: 0.5), value: isPressed)
        }
        .buttonStyle(.plain)
        .simultaneousGesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in isPressed = true }
                .onEnded { _ in isPressed = false }
        )
    }
}
