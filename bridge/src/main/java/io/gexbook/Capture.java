package io.gexbook;

import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import velox.api.layer1.annotations.*;
import velox.api.layer1.data.InstrumentInfo;
import velox.api.layer1.data.TradeInfo;
import velox.api.layer1.simplified.*;

/** Experimental one-instrument capture. No orders or network listener. */
@Layer1SimpleAttachable
@Layer1StrategyName("GEX Paper Capture (experimental)")
@Layer1ApiVersion(Layer1ApiVersionValue.VERSION1)
public class Capture implements CustomModule, DepthDataListener, TradeDataListener, TimeListener {
    private final ArrayBlockingQueue<String> queue = new ArrayBlockingQueue<>(50000);
    private volatile boolean running, failed;
    private Thread writer;
    private long nanos, seq;
    private double pips, sizeDivisor;
    private String symbol, source;
    private boolean resetSent;

    @Override
    public void initialize(String alias, InstrumentInfo info, Api api, InitialState initialState) {
        symbol = System.getProperty("gexbook.symbol", "MNQ");
        source = System.getProperty("gexbook.source", "recorded");
        sizeDivisor = Double.parseDouble(System.getProperty("gexbook.sizeDivisor", "1"));
        if ((!symbol.equals("MNQ") && !symbol.equals("NQ")) ||
            (!source.equals("recorded") && !source.equals("bookmap_bridge")) ||
            !Double.isFinite(sizeDivisor) || sizeDivisor <= 0) {
            throw new IllegalArgumentException("Invalid explicit capture configuration");
        }
        pips = info.pips;
        Path dir = Paths.get(System.getProperty("gexbook.directory", "gexbook-capture"));
        try {
            Files.createDirectories(dir);
            Path output = dir.resolve("capture-" + System.currentTimeMillis() + ".jsonl");
            Files.write(dir.resolve(output.getFileName() + ".metadata.txt"),
                ("SDK alias=" + alias + "\nnormalized symbol=" + symbol +
                 "\npips=" + pips + "\nsize divisor=" + sizeDivisor +
                 "\nsource=" + source + "\n").getBytes(StandardCharsets.UTF_8));
            running = true;
            writer = new Thread(() -> writeLoop(output), "gexbook-paper-capture");
            writer.setDaemon(true);
            writer.start();
        } catch (Exception e) { throw new IllegalStateException("Cannot open capture directory", e); }
    }

    private void writeLoop(Path path) {
        try (BufferedWriter out = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
            while (running || !queue.isEmpty()) {
                String line = queue.poll(100, TimeUnit.MILLISECONDS);
                if (line != null) { out.write(line); out.newLine(); }
                if (queue.isEmpty()) out.flush();
            }
        } catch (Exception e) {
            failed = true; running = false;
            System.err.println("GEX CAPTURE FAILED; paper engine must remain locked: " + e);
        }
    }

    private synchronized void emit(String kind, double price, double size, String side) {
        if (failed || !running) throw new IllegalStateException("Capture unavailable; reload required");
        if (nanos <= 0) throw new IllegalStateException("SDK timestamp unavailable");
        if (!resetSent) {
            resetSent = true;
            enqueue("reset", 0, 0, "");
        }
        enqueue(kind, price, size, side);
    }

    private void enqueue(String kind, double price, double size, String side) {
        String ts = Instant.ofEpochSecond(nanos / 1000000000L, nanos % 1000000000L).toString();
        String line = String.format(Locale.ROOT,
            "{\"seq\":%d,\"ts\":\"%s\",\"kind\":\"%s\",\"symbol\":\"%s\",\"source\":\"%s\",\"price\":%.10f,\"size\":%.10f,\"side\":\"%s\"}",
            seq++, ts, kind, symbol, source, price, size, side);
        if (!queue.offer(line)) {
            failed = true; running = false;
            throw new IllegalStateException("Capture queue overflow; no silent dropping. Reload and rebuild book.");
        }
    }

    @Override public synchronized void onTimestamp(long t) { nanos = t; }
    @Override public void onDepth(boolean isBid, int price, int size) {
        emit("depth", price * pips, size / sizeDivisor, isBid ? "bid" : "ask");
    }
    @Override public void onTrade(double price, int size, TradeInfo info) {
        emit("trade", price, size / sizeDivisor, info.isBidAggressor ? "buy" : "sell");
    }
    @Override public void stop() {
        if (running && !failed && nanos > 0) emit("disconnect", 0, 0, "");
        running = false;
        if (writer != null) {
            try { writer.join(2000); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        }
    }
}
