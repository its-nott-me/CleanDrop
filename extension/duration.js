const params =
    new URLSearchParams(
        window.location.search
    );


const downloadId =
    Number(
        params.get("downloadId")
    );


const notificationId =
    params.get("notificationId");


const durationSelect =
    document.getElementById(
        "duration"
    );


document
    .getElementById("cancel")
    .addEventListener(
        "click",
        () => {

            window.close();

        }
    );


document
    .getElementById("schedule")
    .addEventListener(
        "click",
        async () => {

            const seconds =
                Number(
                    durationSelect.value
                );


            await chrome.runtime.sendMessage({

                type:
                    "custom_delete_duration",

                downloadId,

                seconds,

                notificationId

            });


            window.close();

        }
    );