const DEFAULT_DELETE_SECONDS =
    7 * 24 * 60 * 60;


async function loadSettings() {

    const settings =
        await chrome.storage.local.get({
            defaultDeleteSeconds:
                DEFAULT_DELETE_SECONDS
        });

    document.getElementById(
        "defaultDelete"
    ).value =
        String(settings.defaultDeleteSeconds);
}


async function saveDefaultDeleteTime() {

    const seconds =
        Number(
            document.getElementById(
                "defaultDelete"
            ).value
        );

    await chrome.storage.local.set({
        defaultDeleteSeconds: seconds
    });
}


function sendToCompanion(
    message
) {

    return new Promise((resolve) => {

        chrome.runtime.sendNativeMessage(
            "com.cleandrop.host",
            message,
            response => {

                if (chrome.runtime.lastError) {

                    console.error(
                        chrome.runtime.lastError.message
                    );

                    resolve(null);
                    return;
                }

                resolve(response);
            }
        );
    });
}


async function loadScheduledDownloads() {

    const container =
        document.getElementById(
            "scheduledDownloads"
        );

    container.textContent = "Loading...";


    const response =
        await sendToCompanion({
            event:
                "list_scheduled_deletions"
        });


    if (
        !response ||
        response.status !== "success"
    ) {

        container.textContent =
            "Could not load scheduled deletions.";

        return;
    }


    const downloads =
        response.downloads || [];


    if (downloads.length === 0) {

        container.textContent =
            "No scheduled deletions.";

        return;
    }


    container.innerHTML = "";


    for (const download of downloads) {

        const item =
            document.createElement("div");

        item.className =
            "scheduled-item";


        const filename =
            document.createElement("div");

        filename.className =
            "filename";

        filename.textContent =
            download.original_filename;


        const deleteTime =
            document.createElement("div");

        deleteTime.className =
            "delete-time";

        deleteTime.textContent =
            `Deletes on ${formatDeleteTime(
                download.delete_after
            )}`;


        const cancel =
            document.createElement("button");

        cancel.className =
            "cancel-button";

        cancel.textContent =
            "Cancel";


        cancel.addEventListener(
            "click",
            async () => {

                cancel.disabled = true;

                const response =
                    await sendToCompanion({
                        event:
                            "cancel_deletion",

                        id:
                            download.id
                    });


                if (
                    response?.status ===
                    "success"
                ) {

                    loadScheduledDownloads();

                } else {

                    cancel.disabled = false;

                    alert(
                        response?.message ||
                        "Could not cancel deletion."
                    );
                }
            }
        );


        item.appendChild(filename);
        item.appendChild(deleteTime);
        item.appendChild(cancel);

        container.appendChild(item);
    }
}


function formatDeleteTime(
    timestamp
) {

    const date =
        new Date(timestamp);

    return date.toLocaleString();
}


document
    .getElementById("defaultDelete")
    .addEventListener(
        "change",
        saveDefaultDeleteTime
    );


loadSettings();
loadScheduledDownloads();