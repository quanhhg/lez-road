[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.931718,105.915531,20.977158,105.963905)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.931718,105.915531,20.977158,105.963905);
  node["barrier"](20.931718,105.915531,20.977158,105.963905);
);
(._; >>;);
out meta;
out count;
