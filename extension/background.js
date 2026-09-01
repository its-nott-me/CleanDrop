importScripts(
    "filename-analyzer.js"
);

const HOST_NAME = "com.cleandrop.host";
const pageContexts = new Map();

const DEFAULT_DELETE_SECONDS = 7 * 24 * 60 * 60;


console.log("CleanDrop extension loaded.");


// ============================================================
// NATIVE MESSAGING
// ============================================================

function sendToCompanion(message, onSuccess) {

    chrome.runtime.sendNativeMessage(
        HOST_NAME,
        message,
        response => {

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


            if (
                response?.status === "success" &&
                onSuccess
            ) {

                onSuccess(response);
            }
        }
    );
}



// ============================================================
// DOWNLOAD NOTIFICATION
// ============================================================
function showDownloadNotification(download) {

    const notificationId =
        `cleandrop-download-${download.id}`;


    const filename =
        download.filename
            .split("\\")
            .pop();


    chrome.notifications.create(
        notificationId,
        {
            type: "basic",

            iconUrl: "icon128.png",

            title: "CleanDrop",

            message:
                `${filename} downloaded`,

            buttons: [
                {
                    title: "Schedule delete"
                },
                {
                    title: "Custom 🕒"
                }
            ],

            priority: 1,

            requireInteraction: true
        }
    );
}



// ============================================================
// DOWNLOAD COMPLETION
// ============================================================

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


        // This is the ACTUAL final path
        // chosen through Chrome's Save As.
        const actualPath =
            download.filename;


        const baseName =
            actualPath
                .split("\\")
                .pop();


        // Only worth asking the AI when the name
        // is already generic — reuses the same
        // check used for local rename suggestions.
        const needsAiName =
            isGenericFilename(baseName);


        const pageContext =
            needsAiName
                ? await findBestPageContext(download)
                : null;


        const message = {

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

            ai_enabled:
                needsAiName,

            page_title:
                pageContext?.pageTitle ||
                pageContext?.ogTitle ||
                "",

            page_description:
                pageContext?.description ||
                pageContext?.ogDescription ||
                ""
        };


        sendToCompanion(
            message,

            response => {

                console.log(
                    "Download registered:",
                    response
                );


                showDownloadNotification(
                    download
                );
            }
        );
    }
);



// ============================================================
// FILENAME HANDLING
// ============================================================
//
// For now we don't modify the filename.
// Later this is where our filename analyzer
// can suggest a better name.
//

chrome.downloads.onDeterminingFilename.addListener(
    (
        download,
        suggest
    ) => {

        console.log(
            "Analyzing filename:",
            download.filename
        );


        (async () => {

            const pageContext =
                await findBestPageContext(
                    download
                );


            console.log(
                "[CleanDrop] Matched page context:",
                pageContext
            );


            const enrichedDownload = {

                ...download,

                pageContext

            };


            const result =
                analyzeFilename(
                    enrichedDownload
                );


            console.log(
                "Filename analysis:",
                result
            );


            if (
                !result.changed
            ) {

                suggest();

                return;
            }


            suggest({

                filename:
                    result.filename,

                conflictAction:
                    "uniquify"

            });

        })();


        // Required: tells Chrome that suggest() will be
        // called asynchronously rather than before this
        // listener returns.
        return true;
    }
);



// ============================================================
// NOTIFICATION BUTTONS
// ============================================================

chrome.notifications.onButtonClicked.addListener(
    async (
        notificationId,
        buttonIndex
    ) => {

        if (
            !notificationId.startsWith(
                "cleandrop-download-"
            )
        ) {
            return;
        }


        const downloadId =
            Number(
                notificationId.replace(
                    "cleandrop-download-",
                    ""
                )
            );


        // ==========================================
        // DEFAULT DELETE
        // ==========================================

        if (buttonIndex === 0) {

            console.log(
                "Scheduling deletion with default:",
                downloadId
            );


            scheduleDeletion(
                downloadId,
                DEFAULT_DELETE_SECONDS
            );


            await chrome.notifications.clear(
                notificationId
            );


            return;
        }


        // ==========================================
        // CUSTOM DELETE
        // ==========================================

        if (buttonIndex === 1) {

            console.log(
                "Opening custom duration picker:",
                downloadId
            );


            openDurationPicker(
                downloadId,
                notificationId
            );


            return;
        }

    }
);



// ============================================================
// SCHEDULE DELETION
// ============================================================

async function scheduleDeletion(
    downloadId,
    seconds
) {

    const deleteAfter =
        new Date(
            Date.now() +
            seconds * 1000
        ).toISOString();


    sendToCompanion({

        event:
            "schedule_deletion",

        downloadId:

            downloadId,

        deleteAfter:

            deleteAfter,

        durationSeconds:

            seconds
    },
    response => {

        console.log(
            "Deletion scheduled:",
            response
        );

    });
}



function openDurationPicker(
    downloadId,
    notificationId
) {

    const url =
        chrome.runtime.getURL(
            "duration.html"
        ) +
        `?downloadId=${encodeURIComponent(
            downloadId
        )}` +
        `&notificationId=${encodeURIComponent(
            notificationId
        )}`;


    chrome.windows.create({

        url,

        type: "popup",

        width: 320,

        height: 260,

        focused: true

    });

}



chrome.runtime.onMessage.addListener(
    (
        message,
        sender,
        sendResponse
    ) => {

        if (
            message.type !==
            "custom_delete_duration"
        ) {
            return;
        }


        scheduleDeletion(
            message.downloadId,
            message.seconds
        );


        if (
            message.notificationId
        ) {

            chrome.notifications.clear(
                message.notificationId
            );
        }


        sendResponse({
            status: "success"
        });

    }
);


chrome.runtime.onMessage.addListener(
    (
        message,
        sender
    ) => {

        if (
            message.type !==
            "page_context"
        ) {
            return;
        }


        if (
            !sender.tab ||
            sender.tab.id === undefined
        ) {
            return;
        }


        pageContexts.set(
            sender.tab.id,
            {
                ...message.context,

                updatedAt:
                    Date.now()
            }
        );


        console.log(
            "[CleanDrop] Page context:",
            sender.tab.id,
            message.context
        );
    }
);


async function findBestPageContext(
    download
) {

    const referrer =
        download.referrer || "";

    const downloadUrl =
        download.url || "";


    let referrerOrigin = null;
    let downloadOrigin = null;

    try {
        referrerOrigin =
            referrer
                ? new URL(referrer).origin
                : null;
    } catch {
        // Ignore invalid referrer URL.
    }

    try {
        downloadOrigin =
            downloadUrl
                ? new URL(downloadUrl).origin
                : null;
    } catch {
        // Ignore invalid download URL.
    }


    let bestExact = null;
    let bestReferrerOrigin = null;
    let bestDownloadOrigin = null;


    for (
        const context
        of pageContexts.values()
    ) {

        if (
            !context ||
            !context.updatedAt
        ) {
            continue;
        }


        // Ignore stale contexts.
        if (
            Date.now() -
            context.updatedAt
            > 5 * 60 * 1000
        ) {
            continue;
        }


        // Tier 1: exact page/referrer match.
        if (
            referrer &&
            context.pageUrl === referrer
        ) {

            if (
                !bestExact ||
                context.updatedAt >
                    bestExact.updatedAt
            ) {
                bestExact = context;
            }

            continue;
        }


        let contextOrigin = null;

        try {
            contextOrigin =
                new URL(context.pageUrl).origin;
        } catch {
            continue;
        }


        // Tier 2: same origin as the referring page.
        // This is the common case for downloads whose
        // file itself is served from a different origin
        // than the page (CDNs, image hosts, etc).
        if (
            referrerOrigin &&
            contextOrigin === referrerOrigin
        ) {

            if (
                !bestReferrerOrigin ||
                context.updatedAt >
                    bestReferrerOrigin.updatedAt
            ) {
                bestReferrerOrigin = context;
            }
        }


        // Tier 3: same origin as the downloaded file
        // itself — weaker evidence, only useful when
        // the file is hosted on the same origin as
        // the page (e.g. direct same-site file links).
        if (
            downloadOrigin &&
            contextOrigin === downloadOrigin
        ) {

            if (
                !bestDownloadOrigin ||
                context.updatedAt >
                    bestDownloadOrigin.updatedAt
            ) {
                bestDownloadOrigin = context;
            }
        }
    }


    const passiveMatch =
        bestExact ||
        bestReferrerOrigin ||
        bestDownloadOrigin ||
        null;

    if (passiveMatch) {
        return passiveMatch;
    }


    // Nothing recorded matched — most likely because the
    // background service worker restarted (extension reload,
    // or Chrome suspending it after ~30s idle) and the tab
    // was already open, so content.js never got a chance to
    // re-report. Pull the current tab's info live instead of
    // relying only on what happened to already be recorded.
    return await queryActiveTabContext();
}


async function queryActiveTabContext() {

    try {

        const [tab] = await chrome.tabs.query({
            active: true,
            lastFocusedWindow: true
        });

        if (!tab || !tab.id) {
            return null;
        }

        const [injection] =
            await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: () => {

                    const getMeta = (selector) => {
                        const el =
                            document.querySelector(selector);

                        return el
                            ? el.content || ""
                            : "";
                    };

                    return {
                        pageUrl: window.location.href,
                        pageTitle: document.title || "",
                        description:
                            getMeta('meta[name="description"]'),
                        ogTitle:
                            getMeta('meta[property="og:title"]'),
                        ogDescription:
                            getMeta('meta[property="og:description"]')
                    };
                }
            });

        if (!injection || !injection.result) {
            return null;
        }

        return {
            ...injection.result,
            updatedAt: Date.now()
        };

    } catch (error) {

        console.warn(
            "[CleanDrop] Could not query active tab for context:",
            error
        );

        return null;
    }
}