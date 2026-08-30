importScripts(
    "filename-analyzer.js"
);

const HOST_NAME = "com.cleandrop.host";

const DEFAULT_DELETE_SECONDS = 10
    // 7 * 24 * 60 * 60;


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
                download.endTime
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
    (download, suggest) => {

        console.log(
            "Analyzing filename:",
            download.filename
        );


        const result =
            analyzeFilename(
                download
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


