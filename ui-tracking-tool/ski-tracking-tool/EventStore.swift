//
//  EventStore.swift
//  ski-tracking-tool
//
//  Created by Daniel Lutziger on 06.04.2026.
//

import SwiftUI
import Observation

@Observable
class EventStore {
    var events: [LabelEvent] = [] {
        didSet { save() }
    }

    private let key = "ski_label_events_v2"

    init() { load() }

    func add(_ event: LabelEvent) {
        events.append(event)
        // didSet triggers save automatically
    }

    func clearAll() {
        events.removeAll()
    }

    // MARK: - Persistence

    private func save() {
        if let data = try? JSONEncoder().encode(events) {
            UserDefaults.standard.set(data, forKey: key)
            UserDefaults.standard.synchronize()
        }
    }

    private func load() {
        if let data = UserDefaults.standard.data(forKey: key),
           let decoded = try? JSONDecoder().decode([LabelEvent].self, from: data) {
            events = decoded
        }
    }

    // MARK: - Export

    private var isoFormatter: ISO8601DateFormatter {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }

    func csvString() -> String {
        let header = "event_id,timestamp,activity,ski_type,rating\n"
        let rows = events.enumerated().map { i, e in
            let ts = isoFormatter.string(from: e.timestamp)
            let r = e.rating.map { String($0) } ?? ""
            return "\(i + 1),\(ts),\(e.activity),\(e.skiType ?? ""),\(r)"
        }.joined(separator: "\n")
        return header + rows
    }

    func jsonString() -> String {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? encoder.encode(events),
           let str = String(data: data, encoding: .utf8) {
            return str
        }
        return "[]"
    }

    func csvFileURL() -> URL {
        let name = "ski_labels_\(dateStamp()).csv"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        try? csvString().write(to: url, atomically: true, encoding: .utf8)
        return url
    }

    func jsonFileURL() -> URL {
        let name = "ski_labels_\(dateStamp()).json"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        try? jsonString().write(to: url, atomically: true, encoding: .utf8)
        return url
    }

    private func dateStamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd_HHmmss"
        return f.string(from: Date())
    }

    // MARK: - Stats

    var sessionDate: String {
        guard let first = events.first else { return "No session" }
        let f = DateFormatter()
        f.dateStyle = .medium
        return f.string(from: first.timestamp)
    }

    var skiEventCount: Int {
        events.filter { $0.activity == "ski" && $0.skiType != nil && $0.skiType != "start" }.count
    }

    var averageRating: Double? {
        let rated = events.compactMap { $0.rating }
        guard !rated.isEmpty else { return nil }
        return Double(rated.reduce(0, +)) / Double(rated.count)
    }

    func countFor(_ activity: String) -> Int {
        events.filter { $0.activity == activity }.count
    }

    func ratingDistribution() -> [Int: Int] {
        var dist: [Int: Int] = [:]
        for e in events {
            if let r = e.rating {
                dist[r, default: 0] += 1
            }
        }
        return dist
    }
}
