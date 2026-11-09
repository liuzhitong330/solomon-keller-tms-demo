(function () {
  "use strict";
  // One checked analysis file is the source of every plotted and exported value.
  // Never replace unavailable scientific results with fabricated sample data.
  window.TMS_ANALYSIS_READY = fetch("analysis.json?v=20261109")
    .then(function (response) {
      if (!response.ok) throw new Error("Analysis file could not be loaded (" + response.status + ").");
      return response.json();
    });
}());
