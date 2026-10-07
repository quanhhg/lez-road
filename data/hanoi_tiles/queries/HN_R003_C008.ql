[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.662044,105.625907,20.707406,105.674109)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.662044,105.625907,20.707406,105.674109);
  node["barrier"](20.662044,105.625907,20.707406,105.674109);
);
(._; >>;);
out meta;
out count;
