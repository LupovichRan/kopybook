package dev.kopybook.copybook;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Pattern;

/**
 * COBOL copybook parser (data description entries). Java twin of the Python
 * {@code kopybook.parser}; both are checked against the same golden corpus.
 */
public final class CopybookParser {
    public enum Format { AUTO, FIXED, FREE }

    private static final Map<String, Node.Usage> USAGE = new HashMap<>();
    private static final Set<String> UNSUPPORTED_USAGE = Set.of("NATIONAL", "DISPLAY-1", "INDEX", "POINTER",
            "PROCEDURE-POINTER", "FUNCTION-POINTER", "OBJECT", "COMP-6", "COMPUTATIONAL-6", "UTF-8");
    private static final Set<String> CLAUSE = new HashSet<>(Arrays.asList("PIC", "PICTURE", "USAGE", "REDEFINES",
            "OCCURS", "VALUE", "VALUES", "SIGN", "LEADING", "TRAILING", "SYNC", "SYNCHRONIZED", "JUST", "JUSTIFIED",
            "BLANK", "GLOBAL", "EXTERNAL", "RENAMES", "IS"));
    private static final Map<String, Object> FIGURATIVE = new HashMap<>();

    static {
        for (String s : List.of("DISPLAY")) USAGE.put(s, Node.Usage.DISPLAY);
        for (String s : List.of("COMP", "COMPUTATIONAL", "COMP-4", "COMPUTATIONAL-4", "BINARY")) USAGE.put(s, Node.Usage.BINARY);
        for (String s : List.of("COMP-5", "COMPUTATIONAL-5")) USAGE.put(s, Node.Usage.NATIVE);
        for (String s : List.of("COMP-3", "COMPUTATIONAL-3", "PACKED-DECIMAL")) USAGE.put(s, Node.Usage.PACKED);
        for (String s : List.of("COMP-1", "COMPUTATIONAL-1")) USAGE.put(s, Node.Usage.COMP1);
        for (String s : List.of("COMP-2", "COMPUTATIONAL-2")) USAGE.put(s, Node.Usage.COMP2);
        CLAUSE.addAll(USAGE.keySet());
        CLAUSE.addAll(UNSUPPORTED_USAGE);
        for (String s : List.of("ZERO", "ZEROS", "ZEROES")) FIGURATIVE.put(s, 0L);
        for (String s : List.of("SPACE", "SPACES")) FIGURATIVE.put(s, " ");
        for (String s : List.of("HIGH-VALUE", "HIGH-VALUES")) FIGURATIVE.put(s, "\u00ff");
        for (String s : List.of("LOW-VALUE", "LOW-VALUES", "NULL", "NULLS")) FIGURATIVE.put(s, "\u0000");
        for (String s : List.of("QUOTE", "QUOTES")) FIGURATIVE.put(s, "\"");
    }

    private record Tok(String text, int line, boolean literal, List<Tok> pseudo) {
        Tok(String text, int line, boolean literal) { this(text, line, literal, null); }
    }
    private static final String[] COPY_EXTS = {".cpy", ".CPY", ".cbl", ".CBL", ".cob", ".COB", ".copy", ".txt"};
    private static final int MAX_COPY_DEPTH = 16;
    /**
     * Upper bound (bytes) for any single field and for a whole record. Real z/OS records top out around
     * 32 KB; the cap exists so a hostile or corrupt copybook such as {@code PIC X(999999999)} cannot
     * exhaust memory in the parser or the connector. Must match {@code kopybook.parser.MAX_RECORD_LENGTH}.
     */
    public static final int MAX_RECORD_LENGTH = 1_000_000;
    private record Src(int line, String code) { }

    private CopybookParser() { }

    public static Copybook parse(Path path) throws IOException {
        return parse(path, Format.AUTO, List.of());
    }

    /** Parses a copybook file; COPY members are searched in {@code copyPaths} and then the file's own directory. */
    public static Copybook parse(Path path, Format fmt, List<Path> copyPaths) throws IOException {
        List<Path> paths = new ArrayList<>(copyPaths);
        Path dir = path.toAbsolutePath().getParent();
        if (dir != null) paths.add(dir);
        return parse(Files.readString(path, StandardCharsets.UTF_8), fmt, paths);
    }

    public static Copybook parse(String text) {
        return parse(text, Format.AUTO);
    }

    public static Copybook parse(String text, Format fmt) {
        return parse(text, fmt, List.of());
    }

    public static Copybook parse(String text, Format fmt, List<Path> copyPaths) {
        List<Tok> toks = expandCopy(tokenize(preprocess(text, fmt)), copyPaths, List.of());
        if (toks.isEmpty()) throw new CopybookException("copybook is empty", 0);
        List<Object> entries = new ArrayList<>();
        for (List<Tok> e : splitEntries(toks)) entries.add(parseEntry(e));
        List<Node> roots = buildTree(entries);
        for (Node r : roots) {
            inherit(r, Node.Usage.DISPLAY, false, false);
            resolve(r);
            odoCheck(r);
            offsets(r, 0);
            r.outName = normName(r.name);
            assignOutNames(r);
            Set<String> names = new HashSet<>();
            for (Node n : r.walk()) names.add(n.name);
            for (String[] rn : r.renames)
                for (int i = 1; i < 3; i++)
                    if (rn[i] != null && !names.contains(rn[i]))
                        throw new CopybookException("RENAMES target " + rn[i] + " not found", 0);
        }
        return new Copybook(roots);
    }

    // ------------------------------------------------------------------ source

    private static boolean isFixed(String[] lines) {
        for (String ln : lines) {
            if (ln.isBlank() || ln.length() <= 6) continue;
            if (" *-/Dd".indexOf(ln.charAt(6)) < 0) return false;
        }
        return true;
    }

    private static List<Src> preprocess(String text, Format fmt) {
        String[] lines = text.replace("\t", "    ").split("\r?\n", -1);
        boolean fixed = fmt == Format.AUTO ? isFixed(lines) : fmt == Format.FIXED;
        List<Src> out = new ArrayList<>();
        for (int i = 0; i < lines.length; i++) {
            String ln = lines[i];
            int no = i + 1;
            if (fixed) {
                if (ln.length() < 7) continue;
                char ind = ln.charAt(6);
                String code = ln.substring(7, Math.min(ln.length(), 72));
                if ("*/Dd".indexOf(ind) >= 0) continue;
                if (ind == '-' && !out.isEmpty()) {
                    String cont = code.stripLeading();
                    Src prev = out.get(out.size() - 1);
                    if (!cont.isEmpty() && (cont.charAt(0) == '"' || cont.charAt(0) == '\'')) {
                        String p = prev.code();
                        StringBuilder sb = new StringBuilder(p);
                        while (sb.length() < 65) sb.append(' ');
                        out.set(out.size() - 1, new Src(prev.line(), sb + cont.substring(1)));
                    } else {
                        out.set(out.size() - 1, new Src(prev.line(), prev.code().stripTrailing() + cont));
                    }
                    continue;
                }
                out.add(new Src(no, code));
            } else {
                if (ln.stripLeading().startsWith("*")) continue;
                int j = ln.indexOf("*>");
                out.add(new Src(no, j >= 0 ? ln.substring(0, j) : ln));
            }
        }
        return out;
    }

    private static boolean ws(String s, int i) {
        return i >= s.length() || Character.isWhitespace(s.charAt(i));
    }

    private static List<Tok> tokenize(List<Src> src) {
        List<Tok> toks = new ArrayList<>();
        for (Src s : src) {
            String code = s.code();
            int n = code.length(), i = 0;
            while (i < n) {
                char c = code.charAt(i);
                if (Character.isWhitespace(c)) { i++; continue; }
                if ((c == ',' || c == ';') && ws(code, i + 1)) { i++; continue; }
                if (c == '.' && ws(code, i + 1)) { toks.add(new Tok(".", s.line(), false)); i++; continue; }
                if (code.startsWith("==", i)) {
                    int j = code.indexOf("==", i + 2);
                    if (j < 0) throw new CopybookException("unterminated ==pseudo-text== (it must close on the same line)", s.line());
                    List<Tok> inner = tokenize(List.of(new Src(s.line(), code.substring(i + 2, j))));
                    toks.add(new Tok("==", s.line(), false, inner));
                    i = j + 2;
                    continue;
                }
                boolean hex = "xXzZ".indexOf(c) >= 0 && i + 1 < n && (code.charAt(i + 1) == '"' || code.charAt(i + 1) == '\'');
                if (c == '"' || c == '\'' || hex) {
                    int start = i;
                    if (hex) i++;
                    char q = code.charAt(i++);
                    StringBuilder buf = new StringBuilder();
                    boolean closed = false;
                    while (i < n) {
                        if (code.charAt(i) == q) {
                            if (i + 1 < n && code.charAt(i + 1) == q) { buf.append(q); i += 2; continue; }
                            i++;
                            closed = true;
                            break;
                        }
                        buf.append(code.charAt(i++));
                    }
                    if (!closed) throw new CopybookException("unterminated literal", s.line());
                    String v = buf.toString();
                    if (hex && (code.charAt(start) == 'x' || code.charAt(start) == 'X')) {
                        StringBuilder hb = new StringBuilder();
                        for (int k = 0; k + 1 < v.length(); k += 2)
                            hb.append((char) Integer.parseInt(v.substring(k, k + 2), 16));
                        v = hb.toString();
                    }
                    toks.add(new Tok(v, s.line(), true));
                    continue;
                }
                int j = i;
                while (j < n && !Character.isWhitespace(code.charAt(j))) {
                    char d = code.charAt(j);
                    if (d == '.' && ws(code, j + 1)) break;
                    if ((d == ',' || d == ';') && ws(code, j + 1)) break;
                    j++;
                }
                toks.add(new Tok(code.substring(i, j).toUpperCase(Locale.ROOT), s.line(), false));
                i = j;
            }
        }
        return toks;
    }

    // ------------------------------------------------------------------ COPY / REPLACING

    private record Rep(String mode, List<Tok> pat, List<Tok> by) { }

    /** COPY names are library member names, never paths: reject separators, '..', NUL and absolute paths. */
    private static void checkMemberName(String name, String what, int line) {
        if (name == null || name.isEmpty() || name.contains("/") || name.contains("\\") || name.contains("..")
                || name.indexOf('\0') >= 0 || (name.length() > 1 && name.charAt(1) == ':')) {
            String shown = name == null ? "" : name.length() > 64 ? name.substring(0, 64) : name;
            throw new CopybookException("COPY " + what + " name '" + shown
                    + "' is not a plain member name (path separators and '..' are not allowed)", line);
        }
    }

    /**
     * Returns the real path of a COPY member, guaranteed to lie inside one of the copy directories.
     * Error messages never contain member file contents.
     */
    static Path findMember(String name, String lib, List<Path> paths, int line) {
        checkMemberName(name, "member", line);
        if (lib != null) checkMemberName(lib, "library", line);
        List<String> cands = new ArrayList<>(new LinkedHashSet<>(
                List.of(name, name.toLowerCase(Locale.ROOT), name.toUpperCase(Locale.ROOT))));
        for (Path d : paths) {
            Path root;
            try { root = d.toRealPath(); } catch (IOException e) { continue; }
            if (!Files.isDirectory(root)) continue;
            List<Path> dirs = new ArrayList<>(List.of(root));
            if (lib != null) { dirs.add(root.resolve(lib)); dirs.add(root.resolve(lib.toLowerCase(Locale.ROOT))); }
            for (Path dd : dirs)
                for (String c : cands)
                    for (String e : COPY_EXTS) {
                        Path p = dd.resolve(c + e);
                        if (!Files.isRegularFile(p)) continue;
                        Path real;
                        try { real = p.toRealPath(); }
                        catch (IOException ex) { throw new CopybookException("cannot resolve COPY member " + name, line); }
                        if (!real.startsWith(root))
                            throw new CopybookException("COPY member " + name
                                    + " resolves outside the copy library (symlink escape rejected)", line);
                        return real;
                    }
        }
        throw new CopybookException("COPY member " + name + " not found in " + paths, line);
    }

    private static List<Tok> operand(Tok t) {
        return t.pseudo() != null ? t.pseudo() : List.of(t);
    }

    private static boolean same(Tok a, Tok b) {
        return a.text().equals(b.text()) && a.literal() == b.literal() && a.pseudo() == null && b.pseudo() == null;
    }

    private static List<Tok> applyReplacing(List<Tok> toks, List<Rep> reps) {
        List<Tok> out = new ArrayList<>();
        int i = 0;
        outer:
        while (i < toks.size()) {
            Tok t = toks.get(i);
            for (Rep r : reps) {
                List<Tok> pat = r.pat();
                if (pat.isEmpty()) continue;
                if (r.mode() == null) {
                    boolean m = true;
                    for (int k = 0; k < pat.size() && m; k++) m = i + k < toks.size() && same(toks.get(i + k), pat.get(k));
                    if (m) {
                        for (Tok b : r.by()) out.add(new Tok(b.text(), t.line(), b.literal()));
                        i += pat.size();
                        continue outer;
                    }
                }
                if (pat.size() != 1 || t.literal() || pat.get(0).literal()) continue;
                String p = pat.get(0).text();
                StringBuilder rb = new StringBuilder();
                for (Tok b : r.by()) rb.append(b.text());
                String rs = rb.toString(), tx = t.text();
                String nt = null;
                if ("LEADING".equals(r.mode()) && tx.startsWith(p) && !tx.equals(p)) nt = rs + tx.substring(p.length());
                else if ("TRAILING".equals(r.mode()) && tx.endsWith(p) && !tx.equals(p)) nt = tx.substring(0, tx.length() - p.length()) + rs;
                else if (r.mode() == null && p.contains(":") && tx.contains(p)) nt = tx.replace(p, rs);
                if (nt != null) {
                    out.add(new Tok(nt, t.line(), false));
                    i++;
                    continue outer;
                }
            }
            out.add(t);
            i++;
        }
        return out;
    }

    private static List<Tok> expandCopy(List<Tok> toks, List<Path> paths, List<Path> stack) {
        List<Tok> out = new ArrayList<>();
        int i = 0;
        while (i < toks.size()) {
            Tok t = toks.get(i);
            if (t.literal() || t.pseudo() != null || !t.text().equals("COPY")) { out.add(t); i++; continue; }
            int line = t.line();
            String name, lib = null;
            List<Rep> reps = new ArrayList<>();
            try {
                name = toks.get(i + 1).text();
                i += 2;
                if (toks.get(i).text().equals("OF") || toks.get(i).text().equals("IN")) { lib = toks.get(i + 1).text(); i += 2; }
                if (toks.get(i).text().equals("SUPPRESS")) i++;
                if (toks.get(i).text().equals("REPLACING")) {
                    i++;
                    while (!toks.get(i).text().equals(".") || toks.get(i).pseudo() != null) {
                        String mode = null;
                        Tok m = toks.get(i);
                        if (m.pseudo() == null && (m.text().equals("LEADING") || m.text().equals("TRAILING"))) { mode = m.text(); i++; }
                        List<Tok> a = operand(toks.get(i));
                        if (!toks.get(i + 1).text().equals("BY"))
                            throw new CopybookException("COPY REPLACING: expected BY", toks.get(i + 1).line());
                        reps.add(new Rep(mode, a, operand(toks.get(i + 2))));
                        i += 3;
                    }
                }
                if (!toks.get(i).text().equals(".")) throw new CopybookException("COPY statement must end with a period", toks.get(i).line());
                i++;
            } catch (IndexOutOfBoundsException e) {
                throw new CopybookException("incomplete COPY statement", line);
            }
            if (paths.isEmpty()) throw new CopybookException("COPY " + name + ": no copy library path given", line);
            Path p = findMember(name, lib, paths, line);
            if (stack.contains(p)) throw new CopybookException("recursive COPY of " + name, line);
            if (stack.size() >= MAX_COPY_DEPTH) throw new CopybookException("COPY nesting too deep", line);
            String text;
            try { text = Files.readString(p, StandardCharsets.UTF_8); }
            catch (IOException e) { throw new CopybookException("cannot read COPY member " + name + " (" + e.getClass().getSimpleName() + ")", line); }
            List<Path> st = new ArrayList<>(stack);
            st.add(p);
            out.addAll(applyReplacing(expandCopy(tokenize(preprocess(text, Format.AUTO)), paths, st), reps));
        }
        return out;
    }

    private static List<List<Tok>> splitEntries(List<Tok> toks) {
        List<List<Tok>> out = new ArrayList<>();
        List<Tok> cur = new ArrayList<>();
        for (Tok t : toks) {
            if (!t.literal() && t.text().equals(".")) {
                if (!cur.isEmpty()) out.add(cur);
                cur = new ArrayList<>();
            } else {
                cur.add(t);
            }
        }
        if (!cur.isEmpty()) out.add(cur);
        return out;
    }

    private static final Pattern INT = Pattern.compile("[+-]?\\d+");

    private static Object literal(Tok t) {
        if (t.literal()) return t.text();
        if (FIGURATIVE.containsKey(t.text())) return FIGURATIVE.get(t.text());
        if (INT.matcher(t.text()).matches()) return Long.parseLong(t.text());
        return t.text();
    }

    private static Object parseEntry(List<Tok> ent) {
        Tok first = ent.get(0);
        if (!first.text().matches("\\d{1,2}"))
            throw new CopybookException("expected level number, got '" + first.text() + "'", first.line());
        int level = Integer.parseInt(first.text());
        if (!((level >= 1 && level <= 49) || level == 66 || level == 77 || level == 88))
            throw new CopybookException("invalid level number " + level, first.line());
        int i = 1;
        String name = "FILLER";
        if (i < ent.size() && !ent.get(i).literal() && !CLAUSE.contains(ent.get(i).text())) name = ent.get(i++).text();
        int line = first.line();

        if (level == 88) {
            int j = i;
            if (j < ent.size() && (ent.get(j).text().equals("VALUE") || ent.get(j).text().equals("VALUES"))) j++;
            if (j < ent.size() && (ent.get(j).text().equals("IS") || ent.get(j).text().equals("ARE"))) j++;
            List<Object> vals = new ArrayList<>();
            while (j < ent.size()) {
                Object v = literal(ent.get(j));
                if (j + 2 < ent.size() && !ent.get(j + 1).literal()
                        && (ent.get(j + 1).text().equals("THRU") || ent.get(j + 1).text().equals("THROUGH"))) {
                    vals.add(List.of("THRU", v, literal(ent.get(j + 2))));
                    j += 3;
                } else {
                    vals.add(v);
                    j++;
                }
            }
            if (vals.isEmpty()) throw new CopybookException("88 " + name + " has no VALUE", line);
            return new Condition88(name, vals, line);
        }
        if (level == 66) {
            if (i >= ent.size() || !ent.get(i).text().equals("RENAMES"))
                throw new CopybookException("66 level requires RENAMES", line);
            String start = ent.get(i + 1).text();
            String end = null;
            if (i + 3 < ent.size() && (ent.get(i + 2).text().equals("THRU") || ent.get(i + 2).text().equals("THROUGH")))
                end = ent.get(i + 3).text();
            return new String[] {name, start, end};
        }

        Node node = new Node(level, name, line);
        while (i < ent.size()) {
            Tok tk = ent.get(i);
            String t = tk.text();
            if (tk.literal()) throw new CopybookException("unexpected literal '" + t + "'", tk.line());
            switch (t) {
                case "PIC", "PICTURE" -> {
                    i++;
                    if (ent.get(i).text().equals("IS")) i++;
                    node.pic = Pic.parse(ent.get(i).text(), ent.get(i).line());
                    i++;
                }
                case "USAGE" -> {
                    i++;
                    if (ent.get(i).text().equals("IS")) i++;
                    String u = ent.get(i).text();
                    if (UNSUPPORTED_USAGE.contains(u)) throw new CopybookException.Unsupported("USAGE " + u + " is not supported", line);
                    if (!USAGE.containsKey(u)) throw new CopybookException("unknown USAGE " + u, line);
                    node.usage = USAGE.get(u);
                    i++;
                }
                case "REDEFINES" -> {
                    node.redefines = ent.get(i + 1).text();
                    i += 2;
                }
                case "OCCURS" -> {
                    i++;
                    int lo = Integer.parseInt(ent.get(i++).text());
                    int hi = lo;
                    if (i < ent.size() && ent.get(i).text().equals("TO")) {
                        hi = Integer.parseInt(ent.get(i + 1).text());
                        i += 2;
                    }
                    if (i < ent.size() && ent.get(i).text().equals("TIMES")) i++;
                    if (i < ent.size() && ent.get(i).text().equals("DEPENDING")) {
                        i++;
                        if (ent.get(i).text().equals("ON")) i++;
                        node.dependingOn = ent.get(i++).text();
                    } else if (hi != lo) {
                        throw new CopybookException("OCCURS m TO n requires DEPENDING ON", line);
                    }
                    Set<String> stop = new HashSet<>(CLAUSE);
                    stop.addAll(List.of("ASCENDING", "DESCENDING", "INDEXED"));
                    while (i < ent.size() && List.of("ASCENDING", "DESCENDING", "INDEXED").contains(ent.get(i).text())) {
                        if (ent.get(i).text().equals("INDEXED")) {
                            i++;
                            if (i < ent.size() && ent.get(i).text().equals("BY")) i++;
                        } else {
                            i++;
                            while (i < ent.size() && (ent.get(i).text().equals("KEY") || ent.get(i).text().equals("IS"))) i++;
                        }
                        while (i < ent.size() && !stop.contains(ent.get(i).text())) i++;
                    }
                    node.occursMin = lo;
                    node.occursMax = hi;
                }
                case "SIGN" -> {
                    i++;
                    if (i < ent.size() && ent.get(i).text().equals("IS")) i++;
                }
                case "LEADING", "TRAILING" -> {
                    node.signLeading = t.equals("LEADING");
                    node.signSeparate = false;
                    i++;
                    if (i < ent.size() && ent.get(i).text().equals("SEPARATE")) {
                        node.signSeparate = true;
                        i++;
                        if (i < ent.size() && ent.get(i).text().equals("CHARACTER")) i++;
                    }
                }
                case "VALUE", "VALUES" -> {
                    i++;
                    if (i < ent.size() && (ent.get(i).text().equals("IS") || ent.get(i).text().equals("ARE"))) i++;
                    node.value = literal(ent.get(i++));
                }
                case "SYNC", "SYNCHRONIZED" ->
                        throw new CopybookException.Unsupported("SYNCHRONIZED changes alignment and is not supported", line);
                case "JUST", "JUSTIFIED" -> {
                    i++;
                    if (i < ent.size() && ent.get(i).text().equals("RIGHT")) i++;
                }
                case "BLANK" -> {
                    i++;
                    while (i < ent.size() && List.of("WHEN", "ZERO", "ZEROS", "ZEROES").contains(ent.get(i).text())) i++;
                }
                case "GLOBAL", "EXTERNAL", "IS" -> i++;
                default -> {
                    if (USAGE.containsKey(t)) {
                        node.usage = USAGE.get(t);
                        i++;
                    } else if (UNSUPPORTED_USAGE.contains(t)) {
                        throw new CopybookException.Unsupported("USAGE " + t + " is not supported", line);
                    } else {
                        throw new CopybookException("unexpected token '" + t + "'", tk.line());
                    }
                }
            }
        }
        return node;
    }

    // ------------------------------------------------------------------ tree

    private static List<Node> buildTree(List<Object> entries) {
        List<Node> roots = new ArrayList<>();
        Deque<Node> stack = new ArrayDeque<>();
        Node last = null;
        for (Object e : entries) {
            if (e instanceof Condition88 c) {
                if (last == null) throw new CopybookException("88 level without a preceding item", c.line());
                last.conditions.add(c);
                continue;
            }
            if (e instanceof String[] rn) {
                if (roots.isEmpty()) throw new CopybookException("66 level without a record", 0);
                roots.get(roots.size() - 1).renames.add(rn);
                continue;
            }
            Node node = (Node) e;
            if (node.level == 1 || node.level == 77) {
                stack.clear();
                stack.push(node);
                roots.add(node);
            } else {
                while (!stack.isEmpty() && stack.peek().level >= node.level) stack.pop();
                if (stack.isEmpty()) {
                    Node root = new Node(0, "RECORD", node.line);
                    roots.add(root);
                    stack.push(root);
                }
                Node parent = stack.peek();
                if (parent.pic != null)
                    throw new CopybookException(parent.name + " has a PIC and cannot have subordinate items", node.line);
                node.parent = parent;
                parent.children.add(node);
                stack.push(node);
            }
            last = node;
        }
        return roots;
    }

    private static void inherit(Node n, Node.Usage usage, boolean lead, boolean sep) {
        n.effUsage = n.usage != null ? n.usage : usage;
        boolean l = n.signLeading != null ? n.signLeading : lead;
        boolean s = n.signSeparate != null ? n.signSeparate : sep;
        n.signLeading = l;
        n.signSeparate = s;
        for (Node c : n.children) inherit(c, n.effUsage, l, s);
    }

    private static int binarySize(int digits, int line) {
        if (digits <= 4) return 2;
        if (digits <= 9) return 4;
        if (digits <= 18) return 8;
        throw new CopybookException.Unsupported("binary field with " + digits + " digits (max 18)", line);
    }

    private static int width(Node c) {
        return (int) longWidth(c);
    }

    private static long longWidth(Node c) {
        return (long) c.size * (c.occursMax == null ? 1 : c.occursMax);
    }

    private static void checkCap(long size, String what, int line) {
        if (size > MAX_RECORD_LENGTH)
            throw new CopybookException(what + " is " + size + " bytes, exceeding the maximum record length of "
                    + MAX_RECORD_LENGTH + " bytes", line);
    }

    private static void resolve(Node node) {
        if (!node.children.isEmpty()) {
            if (node.pic != null) throw new CopybookException("group " + node.name + " has a PIC", node.line);
            node.kind = Node.Kind.GROUP;
            for (Node c : node.children) resolve(c);
            Map<String, Node> names = new HashMap<>();
            for (Node c : node.children) names.putIfAbsent(c.name, c);
            List<Node> kids = node.children;
            long size = 0, min = 0;
            int i = 0;
            while (i < kids.size()) {
                Node c = kids.get(i);
                if (c.redefines != null)
                    throw new CopybookException(c.name + " REDEFINES " + c.redefines + ", which does not immediately precede it", c.line);
                long areaMax = longWidth(c);
                long areaMin = (long) c.minSize * (c.occursMax != null ? c.occursMin : 1);
                int j = i + 1;
                while (j < kids.size() && kids.get(j).redefines != null) {
                    Node r = kids.get(j);
                    if (!r.redefines.equals(c.name)) {
                        Node tgt = names.get(r.redefines);
                        if (tgt == null) throw new CopybookException("REDEFINES target " + r.redefines + " not found", r.line);
                        if (!(tgt == c || kids.subList(i + 1, j).contains(tgt)))
                            throw new CopybookException(r.name + " REDEFINES " + r.redefines + ", which does not immediately precede it", r.line);
                    }
                    if (r.dependingOn != null || c.dependingOn != null || r.isVariable() || c.isVariable())
                        throw new CopybookException.Unsupported("REDEFINES involving variable-length data (" + r.name + ")", r.line);
                    c.redefined = true;
                    areaMax = Math.max(areaMax, longWidth(r));
                    j++;
                }
                size += areaMax;
                min += j > i + 1 ? areaMax : areaMin;
                i = j;
            }
            boolean rec = node.level == 0 || node.level == 1 || node.level == 77;
            checkCap(size, (rec ? "record " : "group ") + node.name, node.line);
            node.size = (int) size;
            node.minSize = (int) min;
            return;
        }
        if (node.level == 0) throw new CopybookException("empty record", 0);
        Node.Usage u = node.effUsage;
        if (u == Node.Usage.COMP1 || u == Node.Usage.COMP2) {
            if (node.pic != null) throw new CopybookException(u + " item " + node.name + " must not have a PIC", node.line);
            node.kind = Node.Kind.FLOAT;
            node.size = u == Node.Usage.COMP1 ? 4 : 8;
        } else {
            if (node.pic == null) throw new CopybookException("elementary item " + node.name + " has no PIC", node.line);
            Pic p = node.pic;
            switch (p.kind) {
                case ALNUM, EDITED -> {
                    if (u != Node.Usage.DISPLAY)
                        throw new CopybookException(node.name + ": USAGE " + u + " needs a numeric PIC", node.line);
                    node.kind = p.kind == Pic.Kind.ALNUM ? Node.Kind.ALNUM : Node.Kind.EDITED;
                    node.size = p.length;
                }
                case NUMERIC -> {
                    node.kind = Node.Kind.NUMERIC;
                    node.size = switch (u) {
                        case DISPLAY -> p.digits + (p.signed && node.signSeparate() ? 1 : 0);
                        case BINARY, NATIVE -> binarySize(p.digits, node.line);
                        case PACKED -> p.digits / 2 + 1;
                        default -> throw new IllegalStateException();
                    };
                }
            }
        }
        checkCap(longWidth(node), node.name, node.line);
        node.minSize = node.size;
    }

    private static void odoCheck(Node root) {
        Map<String, Node> byName = new HashMap<>();
        for (Node n : root.walk()) byName.putIfAbsent(n.name, n);
        for (Node n : root.walk()) {
            if (n.dependingOn == null) continue;
            Node obj = byName.get(n.dependingOn);
            if (obj == null) throw new CopybookException("DEPENDING ON object " + n.dependingOn + " not found", n.line);
            if (obj.kind != Node.Kind.NUMERIC) throw new CopybookException("DEPENDING ON object " + n.dependingOn + " is not numeric", n.line);
            if (obj.pic.scale != 0) throw new CopybookException("DEPENDING ON object " + n.dependingOn + " must be an integer", n.line);
        }
    }

    private static void offsets(Node node, int base) {
        node.offset = base;
        if (node.children.isEmpty()) return;
        int cur = base, areaStart = base;
        List<Node> kids = node.children;
        for (int idx = 0; idx < kids.size(); idx++) {
            Node c = kids.get(idx);
            if (c.redefines != null) {
                offsets(c, areaStart);
                continue;
            }
            areaStart = cur;
            offsets(c, cur);
            int w = width(c);
            for (int k = idx + 1; k < kids.size() && kids.get(k).redefines != null; k++) w = Math.max(w, width(kids.get(k)));
            cur += w;
        }
    }

    static String normName(String name) {
        String s = name.toLowerCase(Locale.ROOT).replaceAll("[^A-Za-z0-9_]", "_");
        if (!s.isEmpty() && Character.isDigit(s.charAt(0))) s = "f_" + s;
        return s;
    }

    private static void assignOutNames(Node node) {
        Map<String, Integer> seen = new HashMap<>();
        for (Node c : node.children) {
            if (c.isFiller()) {
                c.outName = "";
            } else {
                String base = normName(c.name);
                int k = seen.getOrDefault(base, 0);
                seen.put(base, k + 1);
                c.outName = k == 0 ? base : base + "_" + (k + 1);
            }
            assignOutNames(c);
        }
    }
}
