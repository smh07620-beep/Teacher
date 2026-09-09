/* Teacher 6.6 M4
 * Post-exam review -> exact learning material / page.
 *
 * Security:
 * - reviewSource is not expected before exam submission.
 * - this file never computes scores or receives answer keys.
 */
(function () {
    'use strict';

    const esc = (value) => String(value ?? '')
        .replace(
            /[&<>"']/g,
            ch => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            })[ch]
        );


    function materialList() {
        try {
            return (
                typeof cachedSlidesList !== 'undefined'
                && Array.isArray(cachedSlidesList)
            )
                ? cachedSlidesList
                : [];
        } catch (_) {
            return [];
        }
    }


    function materialById(id) {
        return materialList().find(
            item =>
                String(item.id)
                === String(id || '')
        ) || null;
    }


    function normalizedSource(source) {
        source =
            source
            && typeof source === 'object'
                ? source
                : {};

        const materialId =
            String(
                source.materialId
                || ''
            ).trim();

        const material =
            materialById(
                materialId
            );

        const materialTitle =
            String(
                source.materialTitle
                || material?.title
                || material?.filename
                || ''
            ).trim();

        const page = Math.max(
            0,
            Number.parseInt(
                source.page
                || 0,
                10
            )
            || 0
        );

        const section =
            String(
                source.section
                || ''
            ).trim();

        const reviewHint =
            String(
                source.reviewHint
                || ''
            ).trim();

        const regionHint =
            String(
                source.regionHint
                || ''
            ).trim();

        let anchorType =
            String(
                source.anchorType
                || ''
            ).trim().toLowerCase();

        let timeSeconds =
            Number.parseFloat(
                source.timeSeconds
                || 0
            );

        if (
            !Number.isFinite(
                timeSeconds
            )
            || timeSeconds < 0
        ) {
            timeSeconds = 0;
        }

        if (
            ![
                'page',
                'time',
                'region',
                'section'
            ].includes(
                anchorType
            )
        ) {
            anchorType = '';
        }

        if (!anchorType) {
            if (page) {
                anchorType = 'page';
            } else if (timeSeconds) {
                anchorType = 'time';
            } else if (regionHint) {
                anchorType = 'region';
            } else if (
                section
                || reviewHint
            ) {
                anchorType = 'section';
            }
        }

        return {
            materialId,
            materialTitle,
            anchorType,
            page,
            timeSeconds,
            regionHint,
            section,
            reviewHint
        };
    }


    function materialDatalist(id) {
        const options =
            materialList()
                .map(material => {
                    const label =
                        material.title
                        || material.filename
                        || material.id;

                    return (
                        `<option value="${esc(material.id)}">`
                        + `${esc(label)}`
                        + `</option>`
                    );
                })
                .join('');

        return (
            `<datalist id="${esc(id)}">`
            + options
            + `</datalist>`
        );
    }


    function reviewSourceFields(
        prefix,
        source = {},
    ) {
        const s =
            normalizedSource(
                source
            );

        const listId =
            `${prefix}-materials`;

        return `
            <div
                class="rounded-xl border border-teal-200 bg-teal-50/50 p-3 space-y-2"
                data-review-source-66="1"
            >
                <div>
                    <div class="text-[11px] font-black text-teal-900">
                        📚 答題後複習來源
                    </div>

                    <div class="text-[10px] text-teal-700 mt-0.5">
                        此資訊只會在學員提交考卷後顯示。
                    </div>
                </div>

                <div class="grid sm:grid-cols-2 gap-2">

                    <label>
                        <span class="text-[11px] font-bold text-slate-600">
                            定位方式
                        </span>

                        <select
                            data-field="reviewAnchorType"
                            class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"
                        >
                            <option value="section" ${s.anchorType === 'section' ? 'selected' : ''}>章節／提示</option>
                            <option value="page" ${s.anchorType === 'page' ? 'selected' : ''}>PPT / PDF 頁碼</option>
                            <option value="time" ${s.anchorType === 'time' ? 'selected' : ''}>影片／音訊時間</option>
                            <option value="region" ${s.anchorType === 'region' ? 'selected' : ''}>圖像／Atlas 區域</option>
                        </select>
                    </label>

                    <label>
                        <span class="text-[11px] font-bold text-slate-600">
                            教材
                        </span>

                        <input
                            data-field="reviewMaterialId"
                            list="${esc(listId)}"
                            value="${esc(s.materialId)}"
                            placeholder="選擇或輸入教材 ID"
                            class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"
                        >

                        ${materialDatalist(listId)}
                    </label>

                    <label>
                        <span class="text-[11px] font-bold text-slate-600">
                            頁碼／投影片
                        </span>

                        <input
                            data-field="reviewPage"
                            type="number"
                            min="1"
                            step="1"
                            value="${s.page || ''}"
                            placeholder="例如 12"
                            class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"
                        >
                    </label>

                    <label>
                        <span class="text-[11px] font-bold text-slate-600">
                            影片／音訊秒數
                        </span>

                        <input
                            data-field="reviewTimeSeconds"
                            type="number"
                            min="0"
                            step="1"
                            value="${s.timeSeconds || ''}"
                            placeholder="例如 155 = 02:35"
                            class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"
                        >
                    </label>

                    <label>
                        <span class="text-[11px] font-bold text-slate-600">
                            圖像重點區域
                        </span>

                        <input
                            data-field="reviewRegionHint"
                            value="${esc(s.regionHint)}"
                            placeholder="例如：影像左下方細胞群"
                            class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"
                        >
                    </label>

                    <label class="sm:col-span-2">
                        <span class="text-[11px] font-bold text-slate-600">
                            建議複習區塊
                        </span>

                        <input
                            data-field="reviewSection"
                            value="${esc(s.section)}"
                            placeholder="例如：QC 異常排除流程／第 3 節"
                            class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"
                        >
                    </label>

                    <label class="sm:col-span-2">
                        <span class="text-[11px] font-bold text-slate-600">
                            加強閱讀提示
                        </span>

                        <textarea
                            data-field="reviewHint"
                            rows="2"
                            placeholder="例如：重新確認校正失敗時的處理順序與何時需重新執行 QC。"
                            class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"
                        >${esc(s.reviewHint)}</textarea>
                    </label>
                </div>
            </div>
        `;
    }


    function sourceFromContainer(
        box,
    ) {
        if (!box) {
            return {};
        }

        const get = field =>
            box.querySelector(
                `[data-field="${field}"]`
            );

        const materialId =
            (
                get(
                    'reviewMaterialId'
                )?.value
                || ''
            ).trim();

        const material =
            materialById(
                materialId
            );

        const page = Math.max(
            0,
            Number.parseInt(
                get(
                    'reviewPage'
                )?.value
                || '0',
                10
            )
            || 0
        );

        const section =
            (
                get(
                    'reviewSection'
                )?.value
                || ''
            ).trim();

        const reviewHint =
            (
                get(
                    'reviewHint'
                )?.value
                || ''
            ).trim();

        const anchorType =
            (
                get(
                    'reviewAnchorType'
                )?.value
                || ''
            ).trim();

        const timeSeconds =
            Math.max(
                0,
                Number.parseFloat(
                    get(
                        'reviewTimeSeconds'
                    )?.value
                    || '0'
                )
                || 0
            );

        const regionHint =
            (
                get(
                    'reviewRegionHint'
                )?.value
                || ''
            ).trim();

        const result = {};

        if (materialId) {
            result.materialId =
                materialId;
        }

        if (material) {
            result.materialTitle =
                material.title
                || material.filename
                || '';
        }

        if (anchorType) {
            result.anchorType =
                anchorType;
        }

        if (page) {
            result.page = page;
        }

        if (timeSeconds) {
            result.timeSeconds =
                timeSeconds;
        }

        if (regionHint) {
            result.regionHint =
                regionHint;
        }

        if (section) {
            result.section =
                section;
        }

        if (reviewHint) {
            result.reviewHint =
                reviewHint;
        }

        return result;
    }


    function hasSource(source) {
        return Boolean(
            source.materialId
            || source.page
            || source.timeSeconds
            || source.regionHint
            || source.section
            || source.reviewHint
        );
    }


    // --------------------------------------------------------
    // Existing-question inline editor
    // --------------------------------------------------------

    if (
        typeof adminQuestionEditFormHTML
        === 'function'
        && !window.__teacher66ReviewEditWrapped
    ) {
        window.__teacher66ReviewEditWrapped =
            true;

        const original =
            adminQuestionEditFormHTML;

        adminQuestionEditFormHTML =
            function (question, catId) {
                let html =
                    original.apply(
                        this,
                        arguments
                    );

                const source =
                    question?.reviewSource
                    || question?.answerConfig
                        ?.reviewSource
                    || {};

                const block =
                    reviewSourceFields(
                        `qreview-${question.id}`,
                        source,
                    );

                const needle =
                    `<div class="flex gap-2"><button id="qsave-${question.id}"`;

                if (
                    html.includes(
                        needle
                    )
                ) {
                    html =
                        html.replace(
                            needle,
                            block
                            + needle
                        );
                } else {
                    const index =
                        html.lastIndexOf(
                            '</div>'
                        );

                    if (index >= 0) {
                        html =
                            html.slice(
                                0,
                                index
                            )
                            + block
                            + html.slice(
                                index
                            );
                    }
                }

                return html;
            };
    }


    if (
        typeof adminPayloadFromQuestionEditor
        === 'function'
        && !window.__teacher66ReviewPayloadWrapped
    ) {
        window.__teacher66ReviewPayloadWrapped =
            true;

        const original =
            adminPayloadFromQuestionEditor;

        adminPayloadFromQuestionEditor =
            function (qId, catId) {
                const payload =
                    original.apply(
                        this,
                        arguments
                    );

                const box =
                    document.getElementById(
                        `qedit-${qId}`
                    );

                const source =
                    sourceFromContainer(
                        box
                    );

                payload.answerConfig = {
                    ...(payload.answerConfig
                        || {})
                };

                if (
                    hasSource(source)
                ) {
                    payload
                        .answerConfig
                        .reviewSource =
                        source;
                } else {
                    delete payload
                        .answerConfig
                        .reviewSource;
                }

                return payload;
            };
    }


    // --------------------------------------------------------
    // New-question form
    // --------------------------------------------------------

    function createFormCatId(
        element,
    ) {
        const id =
            element?.id
            || '';

        const match =
            id.match(
                /^qform-(.+)-explain$/
            );

        return match
            ? match[1]
            : '';
    }


    function injectCreateSource(
        explain,
    ) {
        const catId =
            createFormCatId(
                explain
            );

        if (
            !catId
            || document.getElementById(
                `qreview-create-${catId}`
            )
        ) {
            return;
        }

        const wrap =
            document.createElement(
                'div'
            );

        wrap.id =
            `qreview-create-${catId}`;

        wrap.innerHTML =
            reviewSourceFields(
                `qreview-create-${catId}`,
                {},
            );

        explain.insertAdjacentElement(
            'afterend',
            wrap,
        );
    }


    function scanCreateForms() {
        document
            .querySelectorAll(
                'textarea[id^="qform-"][id$="-explain"]'
            )
            .forEach(
                injectCreateSource
            );
    }


    const observer =
        new MutationObserver(
            scanCreateForms
        );

    observer.observe(
        document.documentElement,
        {
            childList: true,
            subtree: true,
        }
    );

    scanCreateForms();


    function createSourceForCategory(
        catId,
    ) {
        return sourceFromContainer(
            document.getElementById(
                `qreview-create-${catId}`
            )
        );
    }


    // The old create function is retained unchanged.
    // We only enrich its JSON body before it is sent.
    if (
        !window.__teacher66ReviewFetchWrapped
    ) {
        window.__teacher66ReviewFetchWrapped =
            true;

        const originalFetch =
            window.fetch.bind(
                window
            );

        window.fetch =
            function (
                input,
                options = {},
            ) {
                const url =
                    typeof input === 'string'
                        ? input
                        : (
                            input?.url
                            || ''
                        );

                const method =
                    String(
                        options?.method
                        || (
                            typeof input !== 'string'
                                ? input?.method
                                : ''
                        )
                        || 'GET'
                    ).toUpperCase();

                if (
                    url === '/api/quiz-questions'
                    && method === 'POST'
                    && typeof options.body
                        === 'string'
                ) {
                    try {
                        const payload =
                            JSON.parse(
                                options.body
                            );

                        const catId =
                            String(
                                payload
                                    .quizCategoryId
                                || ''
                            );

                        const source =
                            createSourceForCategory(
                                catId
                            );

                        if (
                            hasSource(
                                source
                            )
                        ) {
                            payload.answerConfig = {
                                ...(payload
                                    .answerConfig
                                    || {}),
                                reviewSource:
                                    source,
                            };

                            options = {
                                ...options,
                                body:
                                    JSON.stringify(
                                        payload
                                    ),
                            };
                        }
                    } catch (_) {
                        // Preserve legacy request unchanged.
                    }
                }

                return originalFetch(
                    input,
                    options,
                );
            };
    }


    // --------------------------------------------------------
    // Post-submit question review UI
    // --------------------------------------------------------

    function reviewLabel(source) {
        const bits = [];

        if (
            source.materialTitle
        ) {
            bits.push(
                source.materialTitle
            );
        }

        if (source.page) {
            bits.push(
                `第 ${source.page} 頁／投影片`
            );
        }

        if (source.timeSeconds) {
            const minutes =
                Math.floor(
                    source.timeSeconds / 60
                );

            const seconds =
                Math.floor(
                    source.timeSeconds % 60
                );

            bits.push(
                `時間 ${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
            );
        }

        return bits.join(
            ' · '
        );
    }


    function reviewPanel(
        source,
    ) {
        const panel =
            document.createElement(
                'div'
            );

        panel.dataset.reviewLink66 =
            '1';

        panel.className =
            'rounded-xl border border-teal-200 bg-teal-50/70 p-4 space-y-2';

        const heading =
            document.createElement(
                'div'
            );

        heading.className =
            'font-bold text-teal-900';

        heading.textContent =
            '📚 建議回到教材加強閱讀';

        panel.appendChild(
            heading
        );


        const label =
            reviewLabel(
                source
            );

        if (label) {
            const p =
                document.createElement(
                    'div'
                );

            p.className =
                'text-xs font-semibold text-slate-700';

            p.textContent =
                label;

            panel.appendChild(
                p
            );
        }


        if (source.section) {
            const p =
                document.createElement(
                    'div'
                );

            p.className =
                'text-xs text-slate-600';

            p.textContent =
                `重點區塊：${source.section}`;

            panel.appendChild(
                p
            );
        }

        if (source.regionHint) {
            const p =
                document.createElement(
                    'div'
                );

            p.className =
                'text-xs text-slate-600';

            p.textContent =
                `圖像重點：${source.regionHint}`;

            panel.appendChild(
                p
            );
        }


        if (source.reviewHint) {
            const p =
                document.createElement(
                    'div'
                );

            p.className =
                'text-xs text-teal-800 bg-white/80 border border-teal-100 rounded-lg px-3 py-2';

            p.textContent =
                `複習提示：${source.reviewHint}`;

            panel.appendChild(
                p
            );
        }


        if (source.materialId) {
            const button =
                document.createElement(
                    'button'
                );

            button.type =
                'button';

            button.className =
                'mt-1 inline-flex items-center gap-2 rounded-lg bg-teal-700 hover:bg-teal-600 text-white text-xs font-bold px-4 py-2';

            button.textContent =
                source.page
                    ? `📖 回到教材第 ${source.page} 頁`
                    : '📖 回到教材';

            button.addEventListener(
                'click',
                () => {
                    teacher66OpenReviewSource(
                        source
                    );
                }
            );

            panel.appendChild(
                button
            );
        }

        return panel;
    }


    function teacher66InjectReviewPanels() {
        try {
            if (
                typeof currentCatKey
                === 'undefined'
                || typeof allQuizData
                === 'undefined'
                || typeof isSubmittedMap
                === 'undefined'
                || !isSubmittedMap[
                    currentCatKey
                ]
            ) {
                return;
            }

            const questions =
                allQuizData[
                    currentCatKey
                ]?.questions
                || [];

            questions.forEach(
                (question, index) => {
                    const card =
                        document.getElementById(
                            `question-card-${index}`
                        );

                    if (
                        !card
                        || card.querySelector(
                            '[data-review-link66]'
                        )
                    ) {
                        return;
                    }

                    const source =
                        normalizedSource(
                            question.reviewSource
                            || question
                                .answerConfig
                                ?.reviewSource
                            || {}
                        );

                    if (
                        !hasSource(
                            source
                        )
                    ) {
                        return;
                    }

                    card.appendChild(
                        reviewPanel(
                            source
                        )
                    );
                }
            );
        } catch (
            error
        ) {
            console.warn(
                'Teacher 6.6 review panel:',
                error
            );
        }
    }


    if (
        typeof renderQuestions
        === 'function'
        && !window.__teacher66ReviewRenderWrapped
    ) {
        window.__teacher66ReviewRenderWrapped =
            true;

        const original =
            renderQuestions;

        renderQuestions =
            function () {
                const result =
                    original.apply(
                        this,
                        arguments
                    );

                teacher66InjectReviewPanels();

                return result;
            };
    }


    // --------------------------------------------------------
    // Review button -> materials module
    // --------------------------------------------------------

    function teacher66OpenReviewSource(
        rawSource,
    ) {
        const source =
            normalizedSource(
                rawSource
            );

        if (
            !source.materialId
        ) {
            return;
        }

        let area =
            'internal';

        let group =
            'grpBio';

        try {
            area =
                currentTrainingArea
                || area;

            group =
                currentGroupKey
                || group;
        } catch (_) {}


        const params =
            new URLSearchParams(
                {
                    area,
                    group,
                    module:
                        'materials',
                    from:
                        'exam-review',
                    materialId:
                        source.materialId,
                }
            );

        if (source.anchorType) {
            params.set(
                'anchorType',
                source.anchorType
            );
        }

        if (source.page) {
            params.set(
                'page',
                String(
                    source.page
                )
            );
        }

        if (source.timeSeconds) {
            params.set(
                'timeSeconds',
                String(
                    source.timeSeconds
                )
            );
        }

        if (source.regionHint) {
            params.set(
                'regionHint',
                source.regionHint
            );
        }

        if (source.section) {
            params.set(
                'section',
                source.section
            );
        }

        if (
            source.reviewHint
        ) {
            params.set(
                'reviewHint',
                source.reviewHint
            );
        }

        if (
            source.materialTitle
        ) {
            params.set(
                'materialTitle',
                source.materialTitle
            );
        }

        window.location.href =
            `/system?${params.toString()}`;
    }


    window.teacher66OpenReviewSource =
        teacher66OpenReviewSource;


    // --------------------------------------------------------
    // Materials module deep-link
    // --------------------------------------------------------

    const urlParams =
        new URLSearchParams(
            window.location.search
        );

    const reviewMaterialId =
        urlParams.get(
            'materialId'
        )
        || '';

    const reviewPage =
        Math.max(
            0,
            Number.parseInt(
                urlParams.get(
                    'page'
                )
                || '0',
                10
            )
            || 0
        );

    const reviewAnchorType =
        urlParams.get(
            'anchorType'
        )
        || '';

    const reviewTimeSeconds =
        Math.max(
            0,
            Number.parseFloat(
                urlParams.get(
                    'timeSeconds'
                )
                || '0'
            )
            || 0
        );

    const reviewRegionHint =
        urlParams.get(
            'regionHint'
        )
        || '';

    const reviewSection =
        urlParams.get(
            'section'
        )
        || '';

    const reviewHint =
        urlParams.get(
            'reviewHint'
        )
        || '';

    const reviewMaterialTitle =
        urlParams.get(
            'materialTitle'
        )
        || '';

    let reviewDeepLinkOpened =
        false;


    function syncReaderReviewContext() {
        if (
            !reviewMaterialId
        ) {
            return;
        }

        const base =
            document.getElementById(
                'reader-learning-context'
            );

        if (!base) {
            return;
        }

        let banner =
            document.getElementById(
                'teacher66-review-context'
            );

        if (!banner) {
            banner =
                document.createElement(
                    'div'
                );

            banner.id =
                'teacher66-review-context';

            banner.className =
                'mt-2 rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-xs text-teal-900';

            base.insertAdjacentElement(
                'afterend',
                banner,
            );
        }

        const lines = [];

        if (
            reviewMaterialTitle
        ) {
            lines.push(
                reviewMaterialTitle
            );
        }

        if (reviewPage) {
            lines.push(
                `指定複習：第 ${reviewPage} 頁／投影片`
            );
        }

        if (
            reviewTimeSeconds
        ) {
            const minutes =
                Math.floor(
                    reviewTimeSeconds / 60
                );

            const seconds =
                Math.floor(
                    reviewTimeSeconds % 60
                );

            lines.push(
                `指定時間：${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
            );
        }

        if (
            reviewRegionHint
        ) {
            lines.push(
                `圖像重點：${reviewRegionHint}`
            );
        }

        if (
            reviewSection
        ) {
            lines.push(
                `重點區塊：${reviewSection}`
            );
        }

        if (reviewHint) {
            lines.push(
                `提示：${reviewHint}`
            );
        }

        banner.textContent =
            '🎯 考後複習 ｜ '
            + (
                lines.join(
                    ' ｜ '
                )
                || '請重新閱讀此教材'
            );
    }


    function applyRequestedAnchor() {
        if (!reviewMaterialId) {
            return;
        }

        const material =
            materialById(
                reviewMaterialId
            );

        /*
         * PPT / PDF / image-slide pages
         */
        if (
            reviewPage
            && typeof slideViewerState
                !== 'undefined'
            && String(
                slideViewerState
                    .materialId
                || ''
            )
                === String(
                    reviewMaterialId
                )
        ) {
            const total =
                slideViewerState.mode
                    === 'pdf'
                    ? Number(
                        slideViewerState
                            .pageCount
                        || 0
                    )
                    : Number(
                        slideViewerState
                            .images
                            ?.length
                        || 0
                    );

            if (
                total > 0
                && reviewPage <= total
                && typeof goToSlidePage
                    === 'function'
            ) {
                goToSlidePage(
                    reviewPage - 1
                );
            }
        }


        /*
         * Video / audio:
         * seek after metadata becomes available.
         */
        if (
            reviewTimeSeconds
            && material
        ) {
            const mode =
                material.viewerMode
                || '';

            const media =
                mode === 'audio'
                    ? document.getElementById(
                        'media-audio'
                    )
                    : (
                        mode === 'video'
                            ? document.getElementById(
                                'media-video'
                            )
                            : null
                    );

            if (media) {
                const seek = () => {
                    try {
                        media.currentTime =
                            reviewTimeSeconds;
                    } catch (_) {}
                };

                if (
                    media.readyState >= 1
                ) {
                    seek();
                } else {
                    media.addEventListener(
                        'loadedmetadata',
                        seek,
                        {
                            once: true
                        }
                    );
                }
            }
        }

        syncReaderReviewContext();
    }


    function tryOpenReviewDeepLink() {
        if (
            reviewDeepLinkOpened
            || !reviewMaterialId
        ) {
            return (
                reviewDeepLinkOpened
            );
        }

        const material =
            materialById(
                reviewMaterialId
            );

        if (
            !material
            || typeof openMaterial
                !== 'function'
        ) {
            return false;
        }

        reviewDeepLinkOpened =
            true;

        if (
            material?.materialType === 'atlas'
            && typeof openAtlas
                === 'function'
        ) {
            openAtlas(
                reviewMaterialId
            );
        } else {
            openMaterial(
                reviewMaterialId
            );
        }

        setTimeout(
            applyRequestedAnchor,
            60
        );

        setTimeout(
            applyRequestedAnchor,
            250
        );

        setTimeout(
            applyRequestedAnchor,
            700
        );

        return true;
    }


    if (
        typeof renderSlidesGrid
        === 'function'
        && !window.__teacher66ReviewSlidesWrapped
    ) {
        window.__teacher66ReviewSlidesWrapped =
            true;

        const original =
            renderSlidesGrid;

        renderSlidesGrid =
            async function () {
                const result =
                    await original.apply(
                        this,
                        arguments
                    );

                tryOpenReviewDeepLink();

                return result;
            };
    }


    if (
        typeof teachingSavePage
        === 'function'
        && !window.__teacher66ReviewPageWrapped
    ) {
        window.__teacher66ReviewPageWrapped =
            true;

        const original =
            teachingSavePage;

        teachingSavePage =
            function () {
                const result =
                    original.apply(
                        this,
                        arguments
                    );

                syncReaderReviewContext();

                return result;
            };
    }


    function startDeepLinkRetry() {
        if (
            !reviewMaterialId
        ) {
            return;
        }

        let attempts = 0;

        const timer =
            window.setInterval(
                () => {
                    attempts += 1;

                    if (
                        tryOpenReviewDeepLink()
                        || attempts >= 24
                    ) {
                        window.clearInterval(
                            timer
                        );
                    }
                },
                250
            );
    }


    window.addEventListener(
        'DOMContentLoaded',
        () => {
            scanCreateForms();
            startDeepLinkRetry();
        }
    );

})();
