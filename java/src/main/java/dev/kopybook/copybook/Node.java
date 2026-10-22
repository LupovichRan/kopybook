package dev.kopybook.copybook;

import java.util.ArrayList;
import java.util.List;

/** One data description entry. Elementary items have a PIC (or COMP-1/COMP-2); groups have children. */
public final class Node {
    public enum Usage { DISPLAY, BINARY, NATIVE, PACKED, COMP1, COMP2 }
    public enum Kind { ALNUM, NUMERIC, EDITED, FLOAT, GROUP }

    public final int level;
    public final String name;
    public final int line;
    Pic pic;
    Usage usage;
    Boolean signLeading;
    Boolean signSeparate;
    Integer occursMin;
    Integer occursMax;
    String dependingOn;
    String redefines;
    Object value;
    final List<Node> children = new ArrayList<>();
    final List<Condition88> conditions = new ArrayList<>();
    final List<String[]> renames = new ArrayList<>();
    Node parent;

    Usage effUsage = Usage.DISPLAY;
    Kind kind = Kind.GROUP;
    int size;
    int minSize;
    int offset;
    String outName = "";
    boolean redefined;

    Node(int level, String name, int line) {
        this.level = level;
        this.name = name;
        this.line = line;
    }

    public Pic pic() { return pic; }
    public Usage usage() { return effUsage; }
    public Kind kind() { return kind; }
    public int size() { return size; }
    public int minSize() { return minSize; }
    public int offset() { return offset; }
    public String outName() { return outName; }
    public List<Node> children() { return children; }
    public List<Condition88> conditions() { return conditions; }
    public List<String[]> renames() { return renames; }
    public Integer occursMin() { return occursMin; }
    public Integer occursMax() { return occursMax; }
    public String dependingOn() { return dependingOn; }
    public String redefines() { return redefines; }
    public boolean isRedefined() { return redefined; }
    public boolean signLeading() { return Boolean.TRUE.equals(signLeading); }
    public boolean signSeparate() { return Boolean.TRUE.equals(signSeparate); }
    public Object value() { return value; }

    public boolean isFiller() { return "FILLER".equals(name); }
    public boolean isGroup() { return kind == Kind.GROUP; }
    public boolean isArray() { return occursMax != null; }
    public boolean isVariable() { return minSize != size; }

    public String path() {
        StringBuilder sb = new StringBuilder(name);
        for (Node p = parent; p != null; p = p.parent) sb.insert(0, p.name + ".");
        return sb.toString();
    }

    public List<Node> walk() {
        List<Node> out = new ArrayList<>();
        walk(out);
        return out;
    }

    private void walk(List<Node> out) {
        out.add(this);
        for (Node c : children) c.walk(out);
    }

    @Override
    public String toString() {
        return path();
    }
}
