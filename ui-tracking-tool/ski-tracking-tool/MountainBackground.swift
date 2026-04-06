//
//  MountainBackground.swift
//  ski-tracking-tool
//
//  Created by Daniel Lutziger on 06.04.2026.
//


import SwiftUI

struct MountainBackground: View {
    var body: some View {
        GeometryReader { geo in
            ZStack {
                // Sky gradient
                LinearGradient(
                    colors: [
                        Color(red: 0.12, green: 0.14, blue: 0.22),
                        Color(red: 0.18, green: 0.22, blue: 0.35),
                        Color(red: 0.25, green: 0.32, blue: 0.5),
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )

                // Back mountains (darker, further away)
                MountainLayer(
                    peaks: [0.0, 0.35, 0.55, 0.72, 0.88, 1.0],
                    heights: [0.3, 0.58, 0.42, 0.65, 0.48, 0.32],
                    baseY: 0.75,
                    color: Color(red: 0.15, green: 0.18, blue: 0.28)
                )

                // Mid mountains
                MountainLayer(
                    peaks: [0.0, 0.22, 0.45, 0.62, 0.8, 1.0],
                    heights: [0.18, 0.45, 0.35, 0.52, 0.3, 0.2],
                    baseY: 0.82,
                    color: Color(red: 0.12, green: 0.15, blue: 0.24)
                )

                // Snow caps on mid mountains
                SnowCaps(geo: geo)

                // Front hills (darkest)
                MountainLayer(
                    peaks: [0.0, 0.3, 0.55, 0.75, 1.0],
                    heights: [0.1, 0.25, 0.18, 0.22, 0.12],
                    baseY: 0.9,
                    color: Color(red: 0.09, green: 0.11, blue: 0.18)
                )

                // Bottom fade to pure dark
                VStack {
                    Spacer()
                    LinearGradient(
                        colors: [
                            Color(red: 0.08, green: 0.09, blue: 0.14).opacity(0),
                            Color(red: 0.08, green: 0.09, blue: 0.14),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .frame(height: geo.size.height * 0.2)
                }
            }
        }
        .ignoresSafeArea()
    }
}

struct MountainLayer: View {
    let peaks: [CGFloat]     // x positions (0-1)
    let heights: [CGFloat]   // height at each peak (0-1, from baseY upward)
    let baseY: CGFloat       // baseline y position (0-1)
    let color: Color

    var body: some View {
        GeometryReader { geo in
            Path { path in
                let w = geo.size.width
                let h = geo.size.height
                let base = baseY * h

                path.move(to: CGPoint(x: 0, y: h))
                path.addLine(to: CGPoint(x: 0, y: base - heights[0] * h))

                for i in 0..<peaks.count {
                    let x = peaks[i] * w
                    let y = base - heights[i] * h
                    if i == 0 {
                        path.addLine(to: CGPoint(x: x, y: y))
                    } else {
                        let prevX = peaks[i - 1] * w
                        let midX = (prevX + x) / 2
                        let prevY = base - heights[i - 1] * h
                        path.addQuadCurve(
                            to: CGPoint(x: x, y: y),
                            control: CGPoint(x: midX, y: min(prevY, y) - 15)
                        )
                    }
                }

                path.addLine(to: CGPoint(x: w, y: h))
                path.closeSubpath()
            }
            .fill(color)
        }
    }
}

struct SnowCaps: View {
    let geo: GeometryProxy

    var body: some View {
        let w = geo.size.width
        let h = geo.size.height

        // A few small white triangular shapes near the peaks
        Path { path in
            // Peak 1
            snowCap(path: &path, cx: 0.22 * w, cy: 0.82 * h - 0.45 * h, size: 18)
            // Peak 2
            snowCap(path: &path, cx: 0.62 * w, cy: 0.82 * h - 0.52 * h, size: 22)
            // Peak 3
            snowCap(path: &path, cx: 0.45 * w, cy: 0.82 * h - 0.35 * h, size: 14)
        }
        .fill(Color.white.opacity(0.25))
    }

    private func snowCap(path: inout Path, cx: CGFloat, cy: CGFloat, size: CGFloat) {
        path.move(to: CGPoint(x: cx, y: cy))
        path.addLine(to: CGPoint(x: cx - size, y: cy + size * 0.6))
        path.addQuadCurve(
            to: CGPoint(x: cx + size, y: cy + size * 0.6),
            control: CGPoint(x: cx, y: cy + size * 0.35)
        )
        path.closeSubpath()
    }
}
