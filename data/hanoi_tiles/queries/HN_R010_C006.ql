[out:json][timeout:180][date:"2026-10-01T00:00:00Z"];
way["highway"](20.978632,105.531013,21.023968,105.579291)->.roads;
rel(bw.roads)["type"="restriction"]->.turns;
(
  .roads;
  .turns;
  node["highway"="traffic_signals"](20.978632,105.531013,21.023968,105.579291);
  node["barrier"](20.978632,105.531013,21.023968,105.579291);
);
(._; >>;);
out meta;
out count;
