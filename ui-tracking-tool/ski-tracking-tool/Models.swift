//
//  Models.swift
//  ski-tracking-tool
//
//  Created by Daniel Lutziger on 06.04.2026.
//

import SwiftUI

// MARK: - Label Event

struct LabelEvent: Identifiable, Codable {
    let id: UUID
    let timestamp: Date
    let activity: String
    let skiType: String?
    let rating: Int?

    init(activity: String, skiType: String? = nil, rating: Int? = nil) {
        self.id = UUID()
        self.timestamp = Date()
        self.activity = activity
        self.skiType = skiType
        self.rating = rating
    }
}

// MARK: - Activity

struct Activity: Identifiable {
    let id: String
    let label: String
    let icon: String
    let color: Color
}

let activities: [Activity] = [
    Activity(id: "walk",  label: "Walk",  icon: "figure.walk",            color: Color(red: 0.55, green: 0.6, blue: 0.65)),
    Activity(id: "lift",  label: "Lift",  icon: "arrow.up.right",         color: Color(red: 0.35, green: 0.65, blue: 0.95)),
    Activity(id: "ski",   label: "Ski",   icon: "figure.skiing.downhill", color: Color(red: 0.95, green: 0.3, blue: 0.25)),
    Activity(id: "pause", label: "Pause", icon: "cup.and.saucer.fill",    color: Color(red: 0.9, green: 0.65, blue: 0.2)),
    Activity(id: "other", label: "Other", icon: "pin.fill",               color: Color(red: 0.6, green: 0.4, blue: 0.85)),
]

// MARK: - Ski Type

struct SkiType: Identifiable {
    let id: String
    let label: String
    let icon: String
    let needsRating: Bool
}

let skiTypes: [SkiType] = [
    SkiType(id: "start",        label: "Start run",    icon: "play.fill",               needsRating: false),
    SkiType(id: "carve",        label: "Carve",        icon: "arrow.turn.down.right",   needsRating: true),
    SkiType(id: "short_swings", label: "Short swings", icon: "arrow.left.arrow.right",  needsRating: true),
    SkiType(id: "off_piste",    label: "Off piste",    icon: "mountain.2.fill",         needsRating: true),
    SkiType(id: "carve_short",  label: "Carve + short", icon: "arrow.triangle.swap",    needsRating: true),
    SkiType(id: "general",      label: "General",      icon: "slider.horizontal.3",     needsRating: true),
]

// MARK: - Rating

struct Rating: Identifiable {
    let id: Int
    let label: String
    let emoji: String
    let color: Color
}

let ratings: [Rating] = [
    Rating(id: 0, label: "Accident",  emoji: "🚑", color: Color(red: 0.85, green: 0.15, blue: 0.15)),
    Rating(id: 1, label: "Very bad",  emoji: "😵", color: Color(red: 0.75, green: 0.25, blue: 0.15)),
    Rating(id: 2, label: "Bad",       emoji: "😕", color: Color(red: 0.9,  green: 0.55, blue: 0.15)),
    Rating(id: 3, label: "Okay",      emoji: "😐", color: Color(red: 0.85, green: 0.75, blue: 0.2)),
    Rating(id: 4, label: "Good",      emoji: "🙂", color: Color(red: 0.3,  green: 0.7,  blue: 0.35)),
    Rating(id: 5, label: "Very good", emoji: "🔥", color: Color(red: 0.2,  green: 0.8,  blue: 0.4)),
]

// MARK: - Helpers

func activityFor(_ id: String) -> Activity? {
    activities.first { $0.id == id }
}

func skiTypeLabel(_ id: String) -> String {
    skiTypes.first { $0.id == id }?.label ?? id
}

func displayName(for event: LabelEvent) -> String {
    if event.activity == "ski", let st = event.skiType {
        return "Ski · \(skiTypeLabel(st))"
    }
    return event.activity.capitalized
}
