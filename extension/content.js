// ============================================================
// CleanDrop Page Context Collector
// ============================================================

console.log(
    "[CleanDrop] Content script loaded:",
    location.href
);


// ------------------------------------------------------------
// Basic page context
// ------------------------------------------------------------

function getPageContext() {

    const title =
        document.title?.trim() || "";


    const description =
        document
            .querySelector(
                'meta[name="description"]'
            )
            ?.content
            ?.trim() || "";


    const ogTitle =
        document
            .querySelector(
                'meta[property="og:title"]'
            )
            ?.content
            ?.trim() || "";


    const ogDescription =
        document
            .querySelector(
                'meta[property="og:description"]'
            )
            ?.content
            ?.trim() || "";


    return {

        pageUrl:
            location.href,

        pageTitle:
            title,

        description,

        ogTitle,

        ogDescription
    };
}


// ------------------------------------------------------------
// Send context to background
// ------------------------------------------------------------

function sendPageContext() {

    const context =
        getPageContext();


    chrome.runtime.sendMessage({

        type:
            "page_context",

        context

    });

}


// Send once initially.
sendPageContext();