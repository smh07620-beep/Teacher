/* Phase 3Q · Canonical result export helpers, DOCX fallback, and CSV runtime. */
(function(){
  'use strict';

  let cachedTemplateBuffer = null;
  let pendingExportRecordIndex = null;

  function exporterName() {
    const user = window.TeacherRBAC681?.user || {};
    const profileName = String(user.name || user.username || '').trim();
    if (profileName) return profileName;
    const visibleName = document.getElementById('v573-system-user-name')?.textContent || '';
    return String(visibleName).trim();
  }

  function localDateTime() {
    try {
      return new Date().toLocaleString('zh-TW', {hour12:false});
    } catch (_) {
      return new Date().toISOString().replace('T', ' ').slice(0, 19);
    }
  }

  function buildPaperRetentionMeta(record, groupLabel, quizTitle) {
    const source = record || {};
    const reference = String(source.id || source.attemptId || source.recordId || '').trim();
    return {
      documentTitle: `${groupLabel || ''}年度人員能力考核表`,
      documentReference: reference,
      documentVersion: String(source.quizVersion || source.version || ''),
      groupLabel: groupLabel || '',
      quizTitle: quizTitle || source.quizTitle || '',
      assessmentDate: String(source.timestamp || source.assessmentDate || ''),
      exportedAt: localDateTime(),
      exportedBy: exporterName(),
      paperStatus: '待列印簽核',
      examineeSignature: '________________',
      evaluatorSignature: '________________',
      reviewSignature: '________________',
      signatureDate: '____年__月__日',
      archiveNumber: '________________',
      archiveNote: '列印後請依院內流程完成簽核，並依科內文件管理規範歸檔留存。'
    };
  }

  window.buildRoleCheckboxText = function(role, groupKey = currentGroupKey) {
    const memberRole = getGroupMemberRole(groupKey);
    const duty = role === '值班醫檢師' ? '☑' : '□';
    const member = role === memberRole ? '☑' : '□';
    return `${duty}值班醫檢師 ${member}${memberRole}`;
  };

  window.buildEvaluatorTitleCheckboxText = function(title) {
    const leader = title === '組長' ? '☑' : '□';
    const senior = title === '資深醫檢師' ? '☑' : '□';
    return `${leader}組長 ${senior}資深醫檢師`;
  };

  window.buildCurrentTabDocPayload = function() {
    const nameInput = document.getElementById('examinee-name').value.trim();
    const idInput = document.getElementById('examinee-id').value.trim();
    // The live exam form no longer asks the learner to self-declare a duty role.
    // Leave legacy duty/member checkboxes blank here; persisted-record exports use
    // the server-owned role value through buildRecordDocPayload().
    const roleInput = '';
    const evaluatorNameInput = allQuizData[currentCatKey]?.evaluatorName || '';
    const evaluatorTitleInput = allQuizData[currentCatKey]?.evaluatorTitle || '';
    const quizList = allQuizData[currentCatKey].questions;
    const userAnswers = userAnswersMap[currentCatKey];
    const optionLetters = ['A', 'B', 'C', 'D', 'E', 'F'];
    const answersDetail = quizList.map((q, idx) => {
      const isEssay=(q.questionType||'choice')==='essay';
      const ans=userAnswers[idx];
      return {num:idx+1, questionText:q.question, questionType:isEssay?'essay':'choice', userAnswer:isEssay?(String(ans||'未作答')):(ans!==null && ans!=='' ? optionLetters[ans] : '未作答')};
    });
    const choiceRows=quizList.map((q,idx)=>({q,idx})).filter(x=>(x.q.questionType||'choice')!=='essay');
    const correctCount=choiceRows.filter(x=>userAnswers[x.idx]===x.q.correct).length;
    const wrongCount=choiceRows.length-correctCount;
    const essayCount=quizList.length-choiceRows.length;
    const evaluationScore=quizList.length>0 ? Math.round((correctCount/quizList.length)*100) : 0;
    const passingScore=Math.max(1,Math.min(100,Number(allQuizData[currentCatKey]?.passingScore||80)));
    const evaluationStatus=essayCount>0 ? '待人工批改' : (evaluationScore>=passingScore?'合格':'不合格');
    const groupLabel = GROUPS[currentGroupKey]?.label || currentGroupKey || '';
    const quizTitle = allQuizData[currentCatKey]?.title || '';
    const paperMeta = buildPaperRetentionMeta({
      assessmentDate: localDateTime(),
      quizVersion: allQuizData[currentCatKey]?.version || ''
    }, groupLabel, quizTitle);
    return {
      payload:{
        name:nameInput, empId:idInput,
        role:window.buildRoleCheckboxText(roleInput,currentGroupKey),
        evaluator:evaluatorNameInput,
        evaluatorTitle:window.buildEvaluatorTitleCheckboxText(evaluatorTitleInput),
        score:evaluationScore, evaluationScore, passingScore, correctCount, wrongCount,
        totalQuestions:quizList.length, status:evaluationStatus, result:evaluationStatus,
        questions:answersDetail,
        ...paperMeta
      },
      filenamePart:`${groupLabel}年度人員能力考核表_${quizTitle}_${nameInput}`
    };
  };

  window.buildRecordDocPayload = function(rec) {
    const recordScore = Number.isFinite(Number(rec.score)) ? Number(rec.score) : 0;
    const recordAnswers = Array.isArray(rec.answersDetail) ? rec.answersDetail : [];
    const recordCorrect = recordAnswers.filter(a => a.questionType !== 'essay' && a.isCorrect === true).length;
    const recordWrong = recordAnswers.filter(a => a.questionType !== 'essay' && a.isCorrect === false).length;
    const groupLabel = (GROUPS[rec.groupKey] || GROUPS.grpBio).label;
    const passingScore=Math.max(1,Math.min(100,Number(rec.passingScore||80)));
    const recordStatus=rec.status || (recordScore>=passingScore?'合格':'不合格');
    const paperMeta = buildPaperRetentionMeta(rec, groupLabel, rec.quizTitle || '');
    return {
      payload:{
        name:rec.name, empId:rec.empId,
        role:window.buildRoleCheckboxText(rec.role,rec.groupKey||'grpBio'),
        evaluator:rec.evaluatorName||'',
        evaluatorTitle:window.buildEvaluatorTitleCheckboxText(rec.evaluatorTitle),
        score:recordScore, evaluationScore:recordScore, passingScore,
        correctCount:recordCorrect, wrongCount:recordWrong,
        totalQuestions:recordAnswers.length, status:recordStatus, result:recordStatus,
        questions:recordAnswers,
        ...paperMeta
      },
      filenamePart:`${groupLabel}年度人員能力考核表_${rec.name}_${rec.empId}`
    };
  };

  window.renderDocxFromBuffer = function(templateBuffer, payload, filenamePart) {
    try {
      const zip = new PizZip(templateBuffer);
      const doc = new window.docxtemplater(zip, { paragraphLoop: true, linebreaks: true });
      doc.render(payload);
      const blob = doc.getZip().generate({
        type: 'blob',
        mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      });
      saveAs(blob, `附件1.${filenamePart}.docx`);
      return true;
    } catch (error) {
      console.error(error);
      alert(`匯出失敗：\n${error.message}\n\n請確認範本檔案格式正確（.docx，且佔位字未被 Word 自動校正拆散）。`);
      return false;
    }
  };

  window.exportWithServerTemplate = async function(groupKey, payload, filenamePart, silentMissing=false) {
    try {
      const res = await fetch(`/api/doc-templates/${groupKey}/download`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        if (!silentMissing) alert(data.error || `「${GROUPS[groupKey].label}」尚未設定 Word 匯出範本，請聯絡教學／系統管理者維護 .docx 範本。`);
        return false;
      }
      const buffer = await res.arrayBuffer();
      return window.renderDocxFromBuffer(buffer, payload, filenamePart);
    } catch (err) {
      console.error(err);
      if(!silentMissing) alert(`讀取範本失敗：${err.message}`);
      return false;
    }
  };

  function generateWordFromTemplate(recordIndex) {
    const rec = adminRecords[recordIndex];
    if (!rec) { alert('找不到這筆伺服器成績，請重新整理後台。'); return; }
    const {payload, filenamePart} = window.buildRecordDocPayload(rec);
    if (!window.renderDocxFromBuffer(cachedTemplateBuffer, payload, filenamePart)) {
      cachedTemplateBuffer = null;
    }
  }

  window.exportRecordToWord = async function(recordIndex) {
    const rec = adminRecords[recordIndex];
    if (!rec) { alert('找不到這筆伺服器成績，請重新整理後台。'); return; }
    const groupKey = rec.groupKey || 'grpBio';
    const {payload, filenamePart} = window.buildRecordDocPayload(rec);
    const ok = await window.exportWithServerTemplate(groupKey, payload, filenamePart, groupKey === 'grpBio');
    if (!ok && groupKey === 'grpBio') {
      pendingExportRecordIndex = recordIndex;
      if (cachedTemplateBuffer) {
        generateWordFromTemplate(recordIndex);
      } else {
        alert('後台尚未上傳生化組 Word 範本。可暫時選擇本機「附件1.docx」匯出。');
        document.getElementById('docx-template-input')?.click();
      }
    }
  };

  document.getElementById('docx-template-input')?.addEventListener('change', function(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(loadEvent) {
      cachedTemplateBuffer = loadEvent.target.result;
      if (pendingExportRecordIndex !== null) {
        const index = pendingExportRecordIndex;
        pendingExportRecordIndex = null;
        generateWordFromTemplate(index);
      }
    };
    reader.onerror = function() {
      alert('讀取範本檔案失敗。');
    };
    reader.readAsArrayBuffer(file);
    event.target.value = '';
  });

  window.exportToCSV = async function() {
    try {
      const records = await fetchAdminRecords();
      if (!records || records.length === 0) {
        alert('目前無可供匯出的紀錄！');
        return;
      }
      let csvContent = '\ufeff考核時間,組別,姓名,工號,考試人員類別,考核人員,考核人員職稱,考卷主題,得分,考核結果\n';
      records.forEach(r => {
        csvContent += `"${r.timestamp || ''}","${r.groupLabel || '1 生化組'}","${r.name || ''}","${r.empId || ''}","${r.role || ''}","${r.evaluatorName || ''}","${r.evaluatorTitle || ''}","${r.quizTitle || ''}",${Number(r.score) || 0},"${r.status || ''}"\n`;
      });
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `生化組教育訓練考核成績表_${new Date().toISOString().slice(0,10)}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      alert(`匯出失敗：${error.message}`);
    }
  };
})();
