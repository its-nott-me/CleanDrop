const params = new URLSearchParams(
    window.location.search
);

const requestId = params.get("requestId");

const originalFilename =
    params.get("filename") || "";

const originalPath =
    params.get("path") || "";


const filenameInput =
    document.getElementById("filename");

const originalFilenameElement =
    document.getElementById("originalFilename");

const temporaryCheckbox =
    document.getElementById("temporary");

const expirySection =
    document.getElementById("expirySection");

const expirySelect =
    document.getElementById("expiry");

const downloadButton =
    document.getElementById("download");

const cancelButton =
    document.getElementById("cancel");


originalFilenameElement.textContent =
    originalFilename;

filenameInput.value =
    originalFilename;


temporaryCheckbox.addEventListener(
    "change",
    () => {

        expirySection.classList.toggle(
            "hidden",
            !temporaryCheckbox.checked
        );

    }
);


downloadButton.addEventListener(
    "click",
    async () => {

        const filename =
            filenameInput.value.trim();

        if (!filename) {

            filenameInput.focus();

            return;
        }


        const expirySeconds =
            temporaryCheckbox.checked
                ? Number(expirySelect.value)
                : null;


        await chrome.runtime.sendMessage({

            type: "download_decision",

            requestId,

            accepted: true,

            filename,

            originalPath,

            temporary:
                temporaryCheckbox.checked,

            expirySeconds

        });


        window.close();

    }
);


cancelButton.addEventListener(
    "click",
    async () => {

        await chrome.runtime.sendMessage({

            type: "download_decision",

            requestId,

            accepted: false

        });

        window.close();

    }
);