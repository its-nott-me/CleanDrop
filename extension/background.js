const HOST_NAME = "com.cleandrop.host";
const pendingDownloads = new Map();
const pendingDownloadOptions = new Map();

const DIALOG_WIDTH = 430;
const DIALOG_HEIGHT = 430;

console.log("CleanDrop extension loaded.");


function sendToCompanion(message) {

    chrome.runtime.sendNativeMessage(
        HOST_NAME,
        message,
        (response) => {

            if (chrome.runtime.lastError) {

                console.error(
                    "Native messaging error:",
                    chrome.runtime.lastError.message
                );

                return;
            }

            console.log(
                "Companion response:",
                response
            );

            if (response?.status === "success") {

                showDownloadNotification(
                    {
                        id: message.id,
                        filename: message.filename
                    },
                    response
                );
            }
        }
    );
}

function showDownloadNotification(download, companionResponse) {

    const notificationId =
        `download-${download.id}`;

    chrome.notifications.create(
        notificationId,
        {
            type: "basic",

            iconUrl: "icon128.png",

            title: "CleanDrop",

            message:
                `Downloaded: ${download.filename.split("\\").pop()}`,

            contextMessage:
                "Analyzing download..."
        }
    );
}

chrome.downloads.onChanged.addListener(
    async (delta) => {

        if (
            !delta.state ||
            delta.state.current !== "complete"
        ) {
            return;
        }


        const results =
            await chrome.downloads.search({
                id: delta.id
            });


        if (
            !results ||
            results.length === 0
        ) {
            console.error(
                "Could not find completed download:",
                delta.id
            );

            return;
        }


        const download =
            results[0];


        console.log(
            "FINAL DOWNLOAD:",
            {
                id: download.id,
                filename: download.filename,
                state: download.state,
                exists: download.exists
            }
        );


        const options =
            pendingDownloadOptions.get(
                delta.id
            );


        pendingDownloadOptions.delete(
            delta.id
        );


        // Now we have the actual path.
        const actualPath =
            download.filename;


        // Send the completed download
        // and ACTUAL path to Python.
        sendToCompanion({

            event:
                "download_completed",

            id:
                download.id,

            filename:
                actualPath,

            url:
                download.url,

            referrer:
                download.referrer,

            mime:
                download.mime,

            fileSize:
                download.fileSize,

            startTime:
                download.startTime,

            endTime:
                download.endTime,

            temporary:
                options?.temporary ?? false,

            expirySeconds:
                options?.expirySeconds ?? null,

            requestedFilename:
                options?.requestedFilename ?? null
        });
    }
);

chrome.downloads.onDeterminingFilename.addListener(
    (download, suggest) => {

        const requestId = crypto.randomUUID();

        pendingDownloads.set(requestId, {
            downloadId: download.id,
            suggest: suggest
        });

        const filename =
            download.filename
                .split("\\")
                .pop();

        const dialogUrl =
            chrome.runtime.getURL("dialog.html") +
            `?requestId=${encodeURIComponent(requestId)}` +
            `&filename=${encodeURIComponent(filename)}`;
        
        chrome.windows.create(
            {
                url: dialogUrl,
                type: "popup",
                width: 430,
                height: 430,
                focused: true
            },
            (window) => {

                if (chrome.runtime.lastError) {

                    console.error(
                        "Failed to open CleanDrop dialog:",
                        chrome.runtime.lastError.message
                    );

                    // Fail open: let Chrome continue
                    // with the original filename.
                    pendingDownloads.delete(requestId);

                    suggest();

                    return;
                }

                console.log(
                    "CleanDrop dialog opened:",
                    window.id
                );
            }
        );

        // CRITICAL:
        // Tell Chrome that suggest() will be called later.
        return true;
    }
);

function getExtension(filename) {

    const name =
        filename
            .split("\\")
            .pop();

    const index =
        name.lastIndexOf(".");


    if (index <= 0) {
        return "";
    }


    return name.substring(index);
}

function ensureExtension(
    filename,
    extension
) {

    if (!extension) {
        return filename;
    }


    if (
        filename
            .toLowerCase()
            .endsWith(
                extension.toLowerCase()
            )
    ) {
        return filename;
    }


    return filename + extension;
}

chrome.runtime.onMessage.addListener(
    (message) => {

        if (
            message.type !==
            "download_decision"
        ) {
            return;
        }

        const pending =
            pendingDownloads.get(
                message.requestId
            );

        if (!pending) {
            console.error(
                "Pending download not found:",
                message.requestId
            );

            return;
        }

        pendingDownloads.delete(
            message.requestId
        );

        const {
            downloadId,
            suggest
        } = pending;


        // User cancelled.
        if (!message.accepted) {

            chrome.downloads.cancel(
                downloadId
            );

            return;
        }


        const requestedName =
            message.filename;


        suggest({
            filename: requestedName,
            conflictAction: "uniquify"
        });


        // Save the user's temporary-download
        // preference for after completion.
        pendingDownloadOptions.set(
            downloadId,
            {
                temporary:
                    message.temporary,

                expirySeconds:
                    message.expirySeconds,

                requestedFilename:
                    requestedName
            }
        );
    }
);