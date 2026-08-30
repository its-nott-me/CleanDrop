// ============================================================
// CleanDrop Filename Analyzer
// ============================================================

const GENERIC_FILENAMES = new Set([
    "download",
    "downloaded",
    "file",
    "document",
    "image",
    "images",
    "photo",
    "photos",
    "picture",
    "pictures",
    "video",
    "videos",
    "audio",
    "blob",
    "media",
    "untitled",
    "unknown",
    "screenshot",
    "scan",
    "attachment"
]);


function getBaseName(filename) {

    const name =
        filename
            .split("\\")
            .pop()
            .split("/")
            .pop();

    const lastDot =
        name.lastIndexOf(".");

    if (
        lastDot <= 0
    ) {
        return name;
    }

    return name.substring(
        0,
        lastDot
    );
}


function getExtension(filename) {

    const name =
        filename
            .split("\\")
            .pop()
            .split("/")
            .pop();

    const lastDot =
        name.lastIndexOf(".");

    if (
        lastDot <= 0
    ) {
        return "";
    }

    return name.substring(
        lastDot + 1
    ).toLowerCase();
}


function cleanText(text) {

    return text

        .replace(
            /\.[a-zA-Z0-9]{1,8}$/,
            ""
        )

        .replace(
            /[_-]+/g,
            " "
        )

        .replace(
            /\s+/g,
            " "
        )

        .trim();
}


function isLowInformationFilename(filename) {

    const base =
        getBaseName(filename);


    // Very short names
    if (base.length <= 2) {
        return true;
    }


    // Pure numeric names
    if (/^\d+$/.test(base)) {
        return true;
    }


    // Numeric-heavy names such as:
    // 123456.jpg
    // 00012345.png

    const digits =
        (base.match(/\d/g) || []).length;


    if (
        base.length >= 4 &&
        digits / base.length >= 0.75
    ) {
        return true;
    }


    // Camera-generated names
    if (
        /^(IMG|DSC|DSCN|_DSC|PXL)[-_]?\d+/i
            .test(base)
    ) {
        return true;
    }


    // Screenshot-generated names
    if (
        /^screenshot([_-]|\s|\d)/i
            .test(base)
    ) {
        return true;
    }


    return false;
}


function isGenericFilename(filename) {

    const base =
        cleanText(
            getBaseName(filename)
        ).toLowerCase();


    if (
        GENERIC_FILENAMES.has(base)
    ) {
        return true;
    }


    if (
        /^(image|images|download|file|document|video|audio|photo|picture)\s*\(\d+\)$/i
            .test(base)
    ) {
        return true;
    }


    if (
        /^[a-f0-9]{32}$/i.test(base)
    ) {
        return true;
    }


    if (
        /^[a-f0-9]{40}$/i.test(base)
    ) {
        return true;
    }


    if (
        /^[a-f0-9]{64}$/i.test(base)
    ) {
        return true;
    }


    if (
        /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
            .test(base)
    ) {
        return true;
    }


    if (
        isLowInformationFilename(base)
    ) {
        return true;
    }


    return false;
}


function filenameFromUrl(
    url
) {

    if (!url) {
        return null;
    }


    try {

        const parsed =
            new URL(url);


        const pathname =
            parsed.pathname;


        const lastSegment =
            pathname
                .split("/")
                .filter(Boolean)
                .pop();


        if (!lastSegment) {
            return null;
        }


        const decoded =
            decodeURIComponent(
                lastSegment
            );


        // Avoid treating query-like or meaningless
        // URL segments as filenames.
        if (
            decoded.length < 2 ||
            decoded.length > 150
        ) {
            return null;
        }


        return decoded;

    } catch {

        return null;
    }
}


function sanitizeFilename(
    filename
) {

    return filename

        // Windows-invalid characters
        .replace(
            /[<>:"/\\|?*\x00-\x1F]/g,
            "_"
        )

        .replace(
            /\s+/g,
            " "
        )

        .trim()

        .replace(
            /[. ]+$/,
            ""
        );
}


function preserveExtension(
    suggested,
    original
) {

    const originalExtension =
        getExtension(original);


    if (!originalExtension) {
        return suggested;
    }


    const suggestedExtension =
        getExtension(suggested);


    if (
        suggestedExtension
    ) {
        return suggested;
    }


    return `${suggested}.${originalExtension}`;
}


function analyzeFilename(
    download
) {

    const original =
        download.filename
            .split("\\")
            .pop();


    // --------------------------------------------------------
    // 1. If the existing filename is already meaningful,
    //    leave it alone.
    // --------------------------------------------------------

    if (
        !isGenericFilename(original)
    ) {

        return {
            filename: original,
            changed: false,
            reason: "existing_name"
        };
    }


    // --------------------------------------------------------
    // 2. Try the URL.
    // --------------------------------------------------------

    const urlName =
        filenameFromUrl(
            download.url
        );


    if (
        urlName &&
        !isGenericFilename(urlName)
    ) {

        const clean =
            sanitizeFilename(
                urlName
            );


        const finalName =
            preserveExtension(
                clean,
                original
            );


        return {
            filename: finalName,
            changed: true,
            reason: "url"
        };
    }


    // --------------------------------------------------------
    // 3. No deterministic answer yet.
    //
    // Later:
    // metadata → page title → SLM
    // --------------------------------------------------------

    return {
        filename: original,
        changed: false,
        reason: "no_suggestion"
    };
}