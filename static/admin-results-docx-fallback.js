/* Teacher 7.4 · Local DOCX fallback for result export.
 * Server-side group templates remain the primary path in admin-results-export.js.
 * This keeps only the historical local Attachment-1 fallback for grpBio.
 */
(function(){
  'use strict';

  let cachedTemplateBuffer=null;
  let pendingExportRecordIndex=null;
  let isExportingCurrentTab=false;

  function generateCurrentTabWord(){
    const {payload,filenamePart}=buildCurrentTabDocPayload();
    if(!renderDocxFromBuffer(cachedTemplateBuffer,payload,filenamePart)) cachedTemplateBuffer=null;
  }

  async function exportRecordToWord(recordIndex){
    const record=adminRecords[recordIndex];
    if(!record){alert('找不到這筆伺服器成績，請重新整理後台。');return;}
    const groupKey=record.groupKey||'grpBio';
    const {payload,filenamePart}=buildRecordDocPayload(record);
    const ok=await exportWithServerTemplate(groupKey,payload,filenamePart,groupKey==='grpBio');
    if(!ok&&groupKey==='grpBio'){
      isExportingCurrentTab=false;
      pendingExportRecordIndex=recordIndex;
      if(cachedTemplateBuffer) generateWordFromTemplate(recordIndex);
      else{
        alert('後台尚未上傳生化組 Word 範本。可暫時選擇本機「附件1.docx」匯出。');
        document.getElementById('docx-template-input')?.click();
      }
    }
  }

  function generateWordFromTemplate(recordIndex){
    const record=adminRecords[recordIndex];
    if(!record){alert('找不到這筆伺服器成績，請重新整理後台。');return;}
    const {payload,filenamePart}=buildRecordDocPayload(record);
    if(!renderDocxFromBuffer(cachedTemplateBuffer,payload,filenamePart)) cachedTemplateBuffer=null;
  }

  document.getElementById('docx-template-input')?.addEventListener('change',function(event){
    const file=event.target.files?.[0];
    if(!file)return;
    const reader=new FileReader();
    reader.onload=function(loadEvent){
      cachedTemplateBuffer=loadEvent.target.result;
      if(isExportingCurrentTab){
        generateCurrentTabWord();
      }else if(pendingExportRecordIndex!==null){
        const index=pendingExportRecordIndex;
        pendingExportRecordIndex=null;
        generateWordFromTemplate(index);
      }
    };
    reader.onerror=function(){alert('讀取範本檔案失敗。');};
    reader.readAsArrayBuffer(file);
    event.target.value='';
  });

  window.generateCurrentTabWord=generateCurrentTabWord;
  window.exportRecordToWord=exportRecordToWord;
  window.generateWordFromTemplate=generateWordFromTemplate;
  window.__teacherDocxFallback74={
    markCurrentTabExport(){isExportingCurrentTab=true;},
    clearCurrentTabExport(){isExportingCurrentTab=false;}
  };
})();
