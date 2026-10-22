package dev.kopybook.copybook;

import java.util.List;

/** A parsed copybook: one or more 01-level records. */
public final class Copybook {
    private final List<Node> records;

    Copybook(List<Node> records) {
        this.records = records;
    }

    public List<Node> records() {
        return records;
    }

    public Node record(String name) {
        if (name == null || name.isEmpty()) {
            for (Node r : records) if (r.level != 77) return r;
            throw new CopybookException("no record found", 0);
        }
        for (Node r : records)
            if (r.name.equalsIgnoreCase(name) || r.outName.equals(name)) return r;
        throw new CopybookException("record " + name + " not found", 0);
    }
}
