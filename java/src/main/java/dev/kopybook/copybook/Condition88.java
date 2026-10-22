package dev.kopybook.copybook;

import java.util.List;

/** Level-88 condition name. Values are literals or {"THRU", lo, hi} lists. */
public record Condition88(String name, List<Object> values, int line) { }
