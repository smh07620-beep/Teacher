/* Phase 3X · Learner result-category chart compatibility renderer.
 * The exam runtime continues to own chartInstance; this preserves the global
 * function invoked by both the local and server-authoritative submission flows.
 */
(function(){
  'use strict';

  window.renderCategoryChart = function(categoryStats) {
    const ctx = document.getElementById('categoryChart').getContext('2d');
    if (chartInstance) {
      chartInstance.destroy();
    }

    const labels = Object.keys(categoryStats);
    const userScores = labels.map(cat => categoryStats[cat].correct);
    const maxScores = labels.map(cat => categoryStats[cat].total);

    chartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: '答對題數',
            data: userScores,
            backgroundColor: 'rgba(13, 148, 136, 0.85)',
            borderColor: '#0f766e',
            borderWidth: 1
          },
          {
            label: '該項題數',
            data: maxScores,
            backgroundColor: 'rgba(226, 232, 240, 0.7)',
            borderColor: '#cbd5e1',
            borderWidth: 1
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: { stepSize: 1 }
          }
        },
        plugins: {
          legend: { position: 'top' }
        }
      }
    });
  };
})();
