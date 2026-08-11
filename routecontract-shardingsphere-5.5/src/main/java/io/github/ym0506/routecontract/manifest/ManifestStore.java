package io.github.ym0506.routecontract.manifest;

import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Objects;

/** Explicit-path, atomic storage for candidate and approved observed-execution manifests. */
public final class ManifestStore {

    private final ManifestCodec codec;

    /** Creates a store using the strict canonical manifest codec. */
    public ManifestStore() {
        this(new ManifestCodec());
    }

    /**
     * Creates a store using a caller-supplied codec.
     *
     * @param codec codec used for every read and write
     */
    public ManifestStore(final ManifestCodec codec) {
        this.codec = Objects.requireNonNull(codec, "codec");
    }

    /**
     * Reads a validated manifest from an explicit path.
     *
     * @param manifestFile explicit manifest file path
     * @return validated manifest value
     * @throws IOException when the file cannot be read or the manifest is invalid
     */
    public ObservedExecutionManifest read(final Path manifestFile) throws IOException {
        Path normalized = normalizeFilePath(manifestFile, "manifestFile");
        try (InputStream input = Files.newInputStream(normalized)) {
            return codec.decode(input);
        }
    }

    /**
     * Atomically writes or replaces a candidate while refusing any path that identifies the
     * approved manifest. No approval operation is provided: approval must be an explicit caller
     * file move after review.
     *
     * <p>The operation identifier inside the manifest is never interpreted as a path segment.</p>
     *
     * @param approvedFile explicit protected baseline path; it may not alias {@code candidateFile}
     * @param candidateFile explicit output path for the reviewable candidate
     * @param manifest validated manifest to encode
     * @return the normalized candidate path that was written
     * @throws IOException when directories, temporary storage, synchronization, or atomic move fail
     * @throws IllegalArgumentException when paths identify the same file, use a symbolic-link file,
     *         or do not identify files with parent directories
     */
    public Path writeCandidate(
            final Path approvedFile,
            final Path candidateFile,
            final ObservedExecutionManifest manifest) throws IOException {
        Path approved = normalizeFilePath(approvedFile, "approvedFile");
        Path candidate = normalizeFilePath(candidateFile, "candidateFile");
        Objects.requireNonNull(manifest, "manifest");
        Path approvedParent = approved.getParent();
        Path parent = candidate.getParent();
        if (approvedParent == null || parent == null) {
            throw new IllegalArgumentException("candidateFile must have a parent directory");
        }
        Files.createDirectories(approvedParent);
        Files.createDirectories(parent);
        rejectApprovedAlias(approved, candidate);
        byte[] bytes = codec.encode(manifest);
        Path temporary = Files.createTempFile(parent, ".routecontract-candidate-", ".tmp");
        boolean moved = false;
        try {
            try (FileChannel channel = FileChannel.open(
                    temporary,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
                ByteBuffer buffer = ByteBuffer.wrap(bytes);
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }
                channel.force(true);
            }
            rejectApprovedAlias(approved, candidate);
            Files.move(
                    temporary,
                    candidate,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
            moved = true;
            return candidate;
        } finally {
            if (!moved) {
                Files.deleteIfExists(temporary);
            }
        }
    }

    private static void rejectApprovedAlias(final Path approved, final Path candidate) throws IOException {
        if (Files.isSymbolicLink(approved) || Files.isSymbolicLink(candidate)) {
            throw new IllegalArgumentException("manifest paths must not be symbolic links");
        }
        if (approved.equals(candidate) || resolveThroughExistingParent(approved)
                .equals(resolveThroughExistingParent(candidate))) {
            throw new IllegalArgumentException("candidateFile must differ from approvedFile");
        }
        if (Files.exists(approved, LinkOption.NOFOLLOW_LINKS)
                && Files.exists(candidate, LinkOption.NOFOLLOW_LINKS)
                && Files.isSameFile(approved, candidate)) {
            throw new IllegalArgumentException("candidateFile identifies the approvedFile");
        }
    }

    private static Path resolveThroughExistingParent(final Path path) throws IOException {
        Path parent = path.getParent();
        if (parent == null) {
            throw new IllegalArgumentException("manifest path must have a parent directory");
        }
        return parent.toRealPath().resolve(path.getFileName()).normalize();
    }

    private static Path normalizeFilePath(final Path path, final String label) {
        Objects.requireNonNull(path, label);
        Path normalized = path.toAbsolutePath().normalize();
        if (normalized.getFileName() == null) {
            throw new IllegalArgumentException(label + " must identify a file");
        }
        return normalized;
    }
}
