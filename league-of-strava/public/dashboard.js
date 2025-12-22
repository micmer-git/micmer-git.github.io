let allActivities = [];
let currentPage = 1;
const perPage = 200;
let hasMoreActivities = true;
let currentTotals = null;
let compareTotals = null;
let compareRecentTotals = null;
let compareAthlete = null;
let compareStats = null;

const compareStorageKey = 'stravaCompareAthletes';

async function fetchStravaData(page = 1, per_page = 200) {
  console.log(`Fetching Strava data - Page: ${page}, Per Page: ${per_page}`);
  try {
    const response = await fetch(`/api/strava-data?page=${page}&per_page=${per_page}`);
    if (!response.ok) {
      if (response.status === 401) {
        console.warn('Unauthorized access, redirecting to landing page');
        window.location.href = '/'; // Redirect to landing page if unauthorized
      }
      throw new Error(`Network response was not ok: ${response.statusText}`);
    }
    const data = await response.json();
    console.log('Strava data fetched successfully:', data);
    console.log('Response JSON:', JSON.stringify(data, null, 2)); // Print response JSON to console

    // Append new activities to allActivities
    allActivities = allActivities.concat(data.activities);

    // Display fetched activities
    displayActivities(data.activities);

    // Update totals and ranks
    updateTotalsAndRanks();

    // Update hasMoreActivities flag
    hasMoreActivities = data.hasMore;

    // Show or hide "Load More" button based on hasMoreActivities
    const loadMoreButton = document.getElementById('load-more-button');
    if (hasMoreActivities) {
      loadMoreButton.style.display = 'block';
    } else {
      loadMoreButton.style.display = 'none';
    }

    // Hide "Loading..." indicator after the first load
    if (page === 1) {
      document.getElementById('loading').style.display = 'none'; // Hide loading indicator
      // Show dashboard sections
      document.querySelectorAll('.rank-section, .lifetime-stats, .weekly-stats').forEach(section => {
        section.style.display = 'block';
      });
    }
  } catch (error) {
    console.error('Error fetching Strava data:', error);
    document.getElementById('dashboard-container').innerHTML = '<p>Error loading data.</p>';
  }
}

function updateTotalsAndRanks() {
  // Calculate totals based on allActivities
  const totals = calculateTotals(allActivities);
  currentTotals = totals;
  console.log('Calculated cumulative totals:', totals);

  // Update dashboard stats
  updateDashboardStats(totals);
  updateComparisonDeltas();

  // Recalculate and update ranks
  const rankInfo = calculateRank(totals.hours);
  console.log('Updated Rank Info:', rankInfo);
  updateRankSection(rankInfo);
}

function updateRankSection(rankInfo) {
  // Update Rank Section
  const currentRankElement = document.getElementById('current-rank');
  const rankEmojiElement = document.getElementById('rank-emoji');
  const progressBarElement = document.getElementById('progress-bar');
  const currentRankLabelElement = document.getElementById('current-rank-label');
  const nextRankLabelElement = document.getElementById('next-rank-label');
  const currentPointsElement = document.getElementById('current-points');
  const nextRankPointsElement = document.getElementById('next-rank-points');

  if (!currentRankElement || !rankEmojiElement || !progressBarElement || !currentRankLabelElement || !nextRankLabelElement || !currentPointsElement || !nextRankPointsElement) {
    console.error('One or more rank-related DOM elements are missing.');
    return;
  }

  currentRankElement.textContent = rankInfo.currentRank.name;
  rankEmojiElement.textContent = rankInfo.currentRank.emoji;
  progressBarElement.style.width = `${rankInfo.progressPercent}%`;
  currentRankLabelElement.textContent = rankInfo.currentRank.name;
  nextRankLabelElement.textContent = rankInfo.nextRank.name;
  currentPointsElement.textContent = Math.round(rankInfo.currentPoints);
  nextRankPointsElement.textContent = Math.round(rankInfo.nextRank.minPoints);

  // Populate Rank Tooltip
  const rankListElement = document.getElementById('rank-list');
  if (!rankListElement) {
    console.error('Rank list element is missing.');
  } else {
    rankListElement.innerHTML = '';
    rankConfig.forEach(rank => {
      const li = document.createElement('li');
      li.textContent = `${rank.name} (${rank.minPoints} pts)`;
      rankListElement.appendChild(li);
    });
    console.log('Rank tooltip populated');
  }
}


function updateDashboardStats(totals) {
  // Update Lifetime Stats
  const distanceValueElement = document.getElementById('distance-value');
  const distanceWeekGainElement = document.getElementById('distance-week-gain');
  const elevationValueElement = document.getElementById('elevation-value');
  const elevationWeekGainElement = document.getElementById('elevation-week-gain');
  const caloriesValueElement = document.getElementById('calories-value');
  const caloriesWeekGainElement = document.getElementById('calories-week-gain');

  if (!distanceValueElement || !distanceWeekGainElement || !elevationValueElement || !elevationWeekGainElement || !caloriesValueElement || !caloriesWeekGainElement) {
    console.error('One or more lifetime stats DOM elements are missing.');
  } else {
    distanceValueElement.textContent = `${Math.round(totals.distance / 1000)} 🚴‍♂️`; // Rounded
    distanceWeekGainElement.textContent = `+${Math.round(totals.distanceThisWeek / 1000)} this week`;

    elevationValueElement.textContent = `${Math.round(totals.elevation)} 🏔️`;
    elevationWeekGainElement.textContent = `+${Math.round(totals.elevationThisWeek)} this week`;

    caloriesValueElement.textContent = `${Math.round(totals.calories)} 🍕`;
    caloriesWeekGainElement.textContent = `+${Math.round(totals.caloriesThisWeek)} this week`;
  }

  // Update YTD Stats
  const weeklyHoursElement = document.getElementById('weekly-hours');
  const weeklyDistanceElement = document.getElementById('weekly-distance');
  const weeklyElevationElement = document.getElementById('weekly-elevation');
  const weeklyCaloriesElement = document.getElementById('weekly-calories');

  if (!weeklyHoursElement || !weeklyDistanceElement || !weeklyElevationElement || !weeklyCaloriesElement) {
    console.error('One or more YTD stats DOM elements are missing.');
  } else {
    weeklyHoursElement.textContent = isNaN(totals.hoursThisWeek) ? '0.0 hrs' : `${totals.hoursThisWeek.toFixed(1)} hrs`;
    weeklyDistanceElement.textContent = isNaN(totals.distanceThisWeek) ? '0.0 km' : `${(totals.distanceThisWeek / 1000).toFixed(1)} km`;
    weeklyElevationElement.textContent = isNaN(totals.elevationThisWeek) ? '0 m' : `${totals.elevationThisWeek} m`;
    weeklyCaloriesElement.textContent = isNaN(totals.caloriesThisWeek) ? '0 kcal' : `${totals.caloriesThisWeek} kcal`;
  }
}

function updateComparisonDeltas() {
  const banner = document.getElementById('compare-banner');
  const bannerName = document.getElementById('compare-athlete-name');

  if (!currentTotals || !compareTotals) {
    banner.style.display = 'none';
    bannerName.textContent = '';
    resetCompareDelta('distance-compare-delta');
    resetCompareDelta('elevation-compare-delta');
    resetCompareDelta('calories-compare-delta');
    resetCompareDelta('weekly-hours-compare-delta');
    resetCompareDelta('weekly-distance-compare-delta');
    resetCompareDelta('weekly-elevation-compare-delta');
    resetCompareDelta('weekly-calories-compare-delta');
    return;
  }

  banner.style.display = 'block';
  bannerName.textContent = compareAthlete?.firstname ? `${compareAthlete.firstname} ${compareAthlete.lastname || ''}`.trim() : 'Selected athlete';

  setCompareDelta('distance-compare-delta', currentTotals.distance, compareTotals.distance, 'm');
  setCompareDelta('elevation-compare-delta', currentTotals.elevation, compareTotals.elevation, 'm');
  setCompareDelta('calories-compare-delta', currentTotals.calories, compareTotals.calories, 'kcal');

  setCompareDelta('weekly-hours-compare-delta', currentTotals.hoursThisWeek, compareRecentTotals?.hours, 'hrs');
  setCompareDelta('weekly-distance-compare-delta', currentTotals.distanceThisWeek, compareRecentTotals?.distance, 'm');
  setCompareDelta('weekly-elevation-compare-delta', currentTotals.elevationThisWeek, compareRecentTotals?.elevation, 'm');
  setCompareDelta('weekly-calories-compare-delta', currentTotals.caloriesThisWeek, compareRecentTotals?.calories, 'kcal');
}

function setCompareDelta(elementId, currentValue, otherValue, unit) {
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  if (otherValue === null || otherValue === undefined || Number.isNaN(otherValue)) {
    element.textContent = 'Comparison unavailable';
    element.className = 'compare-delta neutral';
    return;
  }
  const delta = currentValue - otherValue;
  const formattedDelta = formatDelta(delta, unit);
  element.textContent = formattedDelta;
  if (delta > 0) {
    element.className = 'compare-delta positive';
  } else if (delta < 0) {
    element.className = 'compare-delta negative';
  } else {
    element.className = 'compare-delta neutral';
  }
}

function resetCompareDelta(elementId) {
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  element.textContent = '';
  element.className = 'compare-delta';
}

function formatDelta(delta, unit) {
  if (unit === 'm') {
    const kmDelta = delta / 1000;
    return `${kmDelta >= 0 ? '+' : ''}${kmDelta.toFixed(1)} km vs compare`;
  }
  if (unit === 'hrs') {
    return `${delta >= 0 ? '+' : ''}${delta.toFixed(1)} hrs vs compare`;
  }
  return `${delta >= 0 ? '+' : ''}${Math.round(delta)} ${unit} vs compare`;
}


function displayDashboard(data) {
  const stravaData = {
    athlete: data.athlete,
    activities: data.activities,
    totals: data.totals,
  };

  console.log('Rendering dashboard with Strava data');

  // Calculate Rank
  const totalPoints = Number(stravaData.totals.hours) || 0; // Ensure it's a number
  console.log(`Total Points: ${totalPoints}`);

  const rankInfo = calculateRank(totalPoints);
  console.log('Rank Info:', rankInfo);

  // Update Rank Section
  const currentRankElement = document.getElementById('current-rank');
  const rankEmojiElement = document.getElementById('rank-emoji');
  const progressBarElement = document.getElementById('progress-bar');
  const currentRankLabelElement = document.getElementById('current-rank-label');
  const nextRankLabelElement = document.getElementById('next-rank-label');
  const currentPointsElement = document.getElementById('current-points');
  const nextRankPointsElement = document.getElementById('next-rank-points');

  if (!currentRankElement || !rankEmojiElement || !progressBarElement || !currentRankLabelElement || !nextRankLabelElement || !currentPointsElement || !nextRankPointsElement) {
    console.error('One or more rank-related DOM elements are missing.');
    return;
  }

  currentRankElement.textContent = rankInfo.currentRank.name;
  rankEmojiElement.textContent = rankInfo.currentRank.emoji;
  progressBarElement.style.width = `${rankInfo.progressPercent}%`;
  currentRankLabelElement.textContent = rankInfo.currentRank.name;
  nextRankLabelElement.textContent = rankInfo.nextRank.name;
  currentPointsElement.textContent = totalPoints.toFixed(1); // Rounded
  nextRankPointsElement.textContent = rankInfo.nextRank.minPoints;

  // Populate Rank Tooltip
  const rankListElement = document.getElementById('rank-list');
  if (!rankListElement) {
    console.error('Rank list element is missing.');
  } else {
    rankListElement.innerHTML = '';
    rankConfig.forEach(rank => {
      const li = document.createElement('li');
      li.textContent = `${rank.name} (${rank.minPoints} pts)`;
      rankListElement.appendChild(li);
    });
    console.log('Rank tooltip populated');
  }

  // Update YTD Stats (Totals)
  const ytdTotals = stravaData.totals;
  console.log('YTD Totals:', ytdTotals);

  // Get Lifetime Stats
  const lifetimeStats = getLifetimeStats(stravaData.totals, ytdTotals);
  console.log('Lifetime Stats:', lifetimeStats);

  // Update Lifetime Stats Section
  const distanceValueElement = document.getElementById('distance-value');
  const distanceWeekGainElement = document.getElementById('distance-week-gain');
  const elevationValueElement = document.getElementById('elevation-value');
  const elevationWeekGainElement = document.getElementById('elevation-week-gain');
  const caloriesValueElement = document.getElementById('calories-value');
  const caloriesWeekGainElement = document.getElementById('calories-week-gain');

  if (!distanceValueElement || !distanceWeekGainElement || !elevationValueElement || !elevationWeekGainElement || !caloriesValueElement || !caloriesWeekGainElement) {
    console.error('One or more lifetime stats DOM elements are missing.');
  } else {
    distanceValueElement.textContent = `${lifetimeStats.distance.icons} 🚴‍♂️`;
    distanceWeekGainElement.textContent = `+${lifetimeStats.distance.weekGain} this week`;

    elevationValueElement.textContent = `${lifetimeStats.elevation.icons} 🏔️`;
    elevationWeekGainElement.textContent = `+${lifetimeStats.elevation.weekGain} this week`;

    caloriesValueElement.textContent = `${lifetimeStats.calories.icons} 🍕`;
    caloriesWeekGainElement.textContent = `+${lifetimeStats.calories.weekGain} this week`;
  }

  // Update YTD Stats Section
  const weeklyHoursElement = document.getElementById('weekly-hours');
  const weeklyDistanceElement = document.getElementById('weekly-distance');
  const weeklyElevationElement = document.getElementById('weekly-elevation');
  const weeklyCaloriesElement = document.getElementById('weekly-calories');

  if (!weeklyHoursElement || !weeklyDistanceElement || !weeklyElevationElement || !weeklyCaloriesElement) {
    console.error('One or more YTD stats DOM elements are missing.');
  } else {
    weeklyHoursElement.textContent = `${ytdTotals.hours.toFixed(1)} hrs`;
    weeklyDistanceElement.textContent = `${(ytdTotals.distance / 1000).toFixed(1)} km`;
    weeklyElevationElement.textContent = `${ytdTotals.elevation} m`;
    weeklyCaloriesElement.textContent = `${ytdTotals.calories} kcal`;
  }

  console.log('Dashboard rendering complete');

  // Add Event Listeners for Tooltips
  addTooltipListeners();
}

function displayActivities(activities) {
  const activitiesContainer = document.getElementById('activities-container');
  activities.forEach(activity => {
    const activityElement = document.createElement('div');
    activityElement.classList.add('activity-item');
    activityElement.innerHTML = `
      <h3>${activity.name}</h3>
      <p>Date: ${new Date(activity.start_date).toLocaleDateString()}</p>
      <p>Distance: ${(activity.distance / 1000).toFixed(2)} km</p>
      <p>Duration: ${(activity.moving_time / 3600).toFixed(2)} hrs</p>
      <p>Elevation Gain: ${activity.total_elevation_gain} m</p>
      <p>Calories: ${activity.kilojoules || 0} kcal</p>
    `;
    activitiesContainer.appendChild(activityElement);
  });
}

// New Function: Load More Activities
function loadMoreActivities() {
  const activitiesContainer = document.getElementById('activities-container');
  if (!activitiesContainer) {
    console.error('Activities container element is missing.');
    return;
  }

  // Determine the next set of activities to display
  const nextActivities = allActivities.slice(activitiesDisplayed, activitiesDisplayed + activitiesPerLoad);
  if (nextActivities.length === 0) {
    console.log('No more activities to load.');
    document.getElementById('load-more-button').style.display = 'none';
    return;
  }

  nextActivities.forEach(activity => {
    const activityElement = createActivityElement(activity);
    activitiesContainer.appendChild(activityElement);
  });

  activitiesDisplayed += activitiesPerLoad;
  console.log(`Displayed ${activitiesDisplayed} out of ${allActivities.length} activities`);

  // Hide Load More button if all activities are displayed
  if (activitiesDisplayed >= allActivities.length) {
    document.getElementById('load-more-button').style.display = 'none';
  }
}

// New Function: Create Activity Element
function createActivityElement(activity) {
  const activityDiv = document.createElement('div');
  activityDiv.classList.add('activity');

  const date = new Date(activity.start_date);
  const formattedDate = date.toLocaleDateString();

  activityDiv.innerHTML = `
    <h4>${activity.name}</h4>
    <p>Date: ${formattedDate}</p>
    <p>Duration: ${(activity.moving_time / 3600).toFixed(1)} hrs</p>
    <p>Distance: ${(activity.distance / 1000).toFixed(1)} km</p>
    <p>Elevation Gain: ${activity.total_elevation_gain} m</p>
    <p>Calories: ${activity.kilojoules || 0} kcal</p>
  `;

  return activityDiv;
}
document.getElementById('load-more-button').addEventListener('click', () => {
  if (hasMoreActivities) {
    currentPage++;
    fetchStravaData(currentPage, perPage);
  } else {
    console.log('No more activities to load.');
  }
});

function toggleMenu(open) {
  const menu = document.getElementById('dashboard-menu');
  if (!menu) {
    return;
  }
  const shouldOpen = open !== undefined ? open : !menu.classList.contains('open');
  menu.classList.toggle('open', shouldOpen);
  menu.setAttribute('aria-hidden', (!shouldOpen).toString());
}

function getStoredCompareAthletes() {
  const stored = localStorage.getItem(compareStorageKey);
  return stored ? JSON.parse(stored) : [];
}

function storeCompareAthlete(athlete) {
  if (!athlete || !athlete.id) {
    return;
  }
  const stored = getStoredCompareAthletes();
  const existing = stored.find(item => item.id === athlete.id);
  if (!existing) {
    stored.push({ id: athlete.id, name: `${athlete.firstname} ${athlete.lastname || ''}`.trim() });
    localStorage.setItem(compareStorageKey, JSON.stringify(stored));
  }
}

function populateCompareSelect() {
  const select = document.getElementById('compare-user-select');
  if (!select) {
    return;
  }
  const stored = getStoredCompareAthletes();
  select.innerHTML = `
    <option value="">Select athlete</option>
    ${stored.map(item => `<option value="${item.id}">${item.name || item.id}</option>`).join('')}
    <option value="custom">Custom athlete ID</option>
  `;
}

async function fetchCompareData(athleteId) {
  const response = await fetch(`/api/strava-compare?athleteId=${athleteId}`);
  if (!response.ok) {
    throw new Error(`Compare fetch failed: ${response.statusText}`);
  }
  return response.json();
}

function aggregateStats(stats, bucket) {
  const ride = stats[`${bucket}_ride_totals`] || {};
  const run = stats[`${bucket}_run_totals`] || {};
  const swim = stats[`${bucket}_swim_totals`] || {};

  return {
    hours: ((ride.moving_time || 0) + (run.moving_time || 0) + (swim.moving_time || 0)) / 3600 || 0,
    distance: (ride.distance || 0) + (run.distance || 0) + (swim.distance || 0),
    elevation: (ride.elevation_gain || 0) + (run.elevation_gain || 0) + (swim.elevation_gain || 0),
    calories: null,
  };
}

async function handleCompareLoad() {
  const select = document.getElementById('compare-user-select');
  const input = document.getElementById('compare-user-id');
  const status = document.getElementById('compare-status');
  if (!select || !input || !status) {
    return;
  }

  const selectedValue = select.value;
  const athleteId = selectedValue === 'custom' ? input.value.trim() : selectedValue;

  if (!athleteId) {
    status.textContent = 'Please select or enter an athlete ID.';
    return;
  }

  status.textContent = 'Loading comparison...';

  try {
    const data = await fetchCompareData(athleteId);
    compareAthlete = data.athlete;
    compareStats = data.stats;
    compareTotals = aggregateStats(data.stats, 'ytd');
    compareRecentTotals = aggregateStats(data.stats, 'recent');
    storeCompareAthlete(compareAthlete);
    populateCompareSelect();
    updateComparisonDeltas();
    status.textContent = `Comparing with ${compareAthlete.firstname} ${compareAthlete.lastname || ''}`.trim();
  } catch (error) {
    console.error('Comparison fetch failed', error);
    status.textContent = 'Unable to load comparison. Check athlete ID and access.';
  }
}

function handleCompareClear() {
  compareTotals = null;
  compareRecentTotals = null;
  compareAthlete = null;
  compareStats = null;
  const status = document.getElementById('compare-status');
  if (status) {
    status.textContent = 'Comparison cleared.';
  }
  updateComparisonDeltas();
}
function renderRanksAndStats(data) {
  console.log('Rendering dashboard with Strava data');

  // Calculate Rank
  const totalPoints = Number(data.totals.hours) || 0; // Ensure it's a number
  console.log(`Total Points: ${totalPoints}`);

  const rankInfo = calculateRank(totalPoints);
  console.log('Rank Info:', rankInfo);

  // Update Rank Section
  const currentRankElement = document.getElementById('current-rank');
  const rankEmojiElement = document.getElementById('rank-emoji');
  const progressBarElement = document.getElementById('progress-bar');
  const currentRankLabelElement = document.getElementById('current-rank-label');
  const nextRankLabelElement = document.getElementById('next-rank-label');
  const currentPointsElement = document.getElementById('current-points');
  const nextRankPointsElement = document.getElementById('next-rank-points');

  if (!currentRankElement || !rankEmojiElement || !progressBarElement || !currentRankLabelElement || !nextRankLabelElement || !currentPointsElement || !nextRankPointsElement) {
    console.error('One or more rank-related DOM elements are missing.');
    return;
  }

  currentRankElement.textContent = rankInfo.currentRank.name;
  rankEmojiElement.textContent = rankInfo.currentRank.emoji;
  progressBarElement.style.width = `${rankInfo.progressPercent}%`;
  currentRankLabelElement.textContent = rankInfo.currentRank.name;
  nextRankLabelElement.textContent = rankInfo.nextRank.name;
  currentPointsElement.textContent = totalPoints;
  nextRankPointsElement.textContent = rankInfo.nextRank.minPoints;

  // Populate Rank Tooltip
  const rankListElement = document.getElementById('rank-list');
  if (!rankListElement) {
    console.error('Rank list element is missing.');
  } else {
    rankListElement.innerHTML = '';
    rankConfig.forEach(rank => {
      const li = document.createElement('li');
      li.textContent = `${rank.name} (${rank.minPoints} pts)`;
      rankListElement.appendChild(li);
    });
    console.log('Rank tooltip populated');
  }

  // YTD Totals
  const ytdTotals = data.totals;
  console.log('YTD Totals:', ytdTotals);

  // Get Lifetime Stats
  const lifetimeStats = getLifetimeStats(data.totals, ytdTotals);
  console.log('Lifetime Stats:', lifetimeStats);

  // Update Lifetime Stats Section
  const distanceValueElement = document.getElementById('distance-value');
  const distanceWeekGainElement = document.getElementById('distance-week-gain');
  const elevationValueElement = document.getElementById('elevation-value');
  const elevationWeekGainElement = document.getElementById('elevation-week-gain');
  const caloriesValueElement = document.getElementById('calories-value');
  const caloriesWeekGainElement = document.getElementById('calories-week-gain');

  if (!distanceValueElement || !distanceWeekGainElement || !elevationValueElement || !elevationWeekGainElement || !caloriesValueElement || !caloriesWeekGainElement) {
    console.error('One or more lifetime stats DOM elements are missing.');
  } else {
    distanceValueElement.textContent = `${lifetimeStats.distance.icons} 🚴‍♂️`;
    distanceWeekGainElement.textContent = `+${lifetimeStats.distance.weekGain} this week`;

    elevationValueElement.textContent = `${lifetimeStats.elevation.icons} 🏔️`;
    elevationWeekGainElement.textContent = `+${lifetimeStats.elevation.weekGain} this week`;

    caloriesValueElement.textContent = `${lifetimeStats.calories.icons} 🍕`;
    caloriesWeekGainElement.textContent = `+${lifetimeStats.calories.weekGain} this week`;
  }

  // Update YTD Stats
  const weeklyHoursElement = document.getElementById('weekly-hours');
  const weeklyDistanceElement = document.getElementById('weekly-distance');
  const weeklyElevationElement = document.getElementById('weekly-elevation');
  const weeklyCaloriesElement = document.getElementById('weekly-calories');

  if (!weeklyHoursElement || !weeklyDistanceElement || !weeklyElevationElement || !weeklyCaloriesElement) {
    console.error('One or more YTD stats DOM elements are missing.');
  } else {
    weeklyHoursElement.textContent = isNaN(ytdTotals.hours) ? '0.0 hrs' : `${ytdTotals.hours.toFixed(1)} hrs`;
    weeklyDistanceElement.textContent = isNaN(ytdTotals.distance) ? '0.0 km' : `${(ytdTotals.distance / 1000).toFixed(1)} km`;
    weeklyElevationElement.textContent = isNaN(ytdTotals.elevation) ? '0 m' : `${ytdTotals.elevation} m`;
    weeklyCaloriesElement.textContent = isNaN(ytdTotals.calories) ? '0 kcal' : `${ytdTotals.calories} kcal`;
  }

  console.log('Dashboard rendering complete');

  // Add Event Listeners for Tooltips
  addTooltipListeners();
}

function calculateTotals(activities) {
  // Implement YTD filtering
  const currentYear = new Date().getFullYear();
  const startOfYear = new Date(currentYear, 0, 1); // January 1st
  const today = new Date();

  const ytdActivities = activities.filter(activity => {
    const activityDate = new Date(activity.start_date);
    return activityDate >= startOfYear && activityDate <= today;
  });

  let totals = {
    hours: 0,
    distance: 0, // in meters
    elevation: 0, // in meters
    calories: 0, // in kilojoules or as per Strava's data
    activities: ytdActivities.length,
    hoursThisWeek: 0,
    distanceThisWeek: 0,
    elevationThisWeek: 0,
    caloriesThisWeek: 0,
  };

  ytdActivities.forEach(activity => {
    totals.hours += activity.moving_time / 3600;
    totals.distance += activity.distance;
    totals.elevation += activity.total_elevation_gain;
    totals.calories += activity.kilojoules || 0;
  });

  // Calculate 'This Week' totals
  const oneWeekAgo = new Date();
  oneWeekAgo.setDate(today.getDate() - 7);

  const weekActivities = ytdActivities.filter(activity => {
    const activityDate = new Date(activity.start_date);
    return activityDate >= oneWeekAgo && activityDate <= today;
  });

  weekActivities.forEach(activity => {
    totals.hoursThisWeek += activity.moving_time / 3600;
    totals.distanceThisWeek += activity.distance;
    totals.elevationThisWeek += activity.total_elevation_gain;
    totals.caloriesThisWeek += activity.kilojoules || 0;
  });

  console.log('Calculated YTD Totals:', totals);
  return totals;
}

// Existing displayData function from your previous code
function displayData(stravaData) {
  console.log('Rendering dashboard with Strava data');

  // Calculate Rank
  const totalPoints = stravaData.totals.hours; // Or any other logic
  console.log(`Total Points: ${totalPoints}`);

  const rankInfo = calculateRank(totalPoints);
  console.log('Rank Info:', rankInfo);

  // Update Rank Section
  const currentRankElement = document.getElementById('current-rank');
  const rankEmojiElement = document.getElementById('rank-emoji');
  const progressBarElement = document.getElementById('progress-bar');
  const currentRankLabelElement = document.getElementById('current-rank-label');
  const nextRankLabelElement = document.getElementById('next-rank-label');
  const currentPointsElement = document.getElementById('current-points');
  const nextRankPointsElement = document.getElementById('next-rank-points');

  if (!currentRankElement || !rankEmojiElement || !progressBarElement || !currentRankLabelElement || !nextRankLabelElement || !currentPointsElement || !nextRankPointsElement) {
    console.error('One or more rank-related DOM elements are missing.');
    return;
  }

  currentRankElement.textContent = rankInfo.currentRank.name;
  rankEmojiElement.textContent = rankInfo.currentRank.emoji;
  progressBarElement.style.width = `${rankInfo.progressPercent}%`;
  currentRankLabelElement.textContent = rankInfo.currentRank.name;
  nextRankLabelElement.textContent = rankInfo.nextRank.name;
  currentPointsElement.textContent = totalPoints;
  nextRankPointsElement.textContent = rankInfo.nextRank.minPoints;

  // Populate Rank Tooltip
  const rankListElement = document.getElementById('rank-list');
  if (!rankListElement) {
    console.error('Rank list element is missing.');
  } else {
    rankListElement.innerHTML = '';
    rankConfig.forEach(rank => {
      const li = document.createElement('li');
      li.textContent = `${rank.name} (${rank.minPoints} pts)`;
      rankListElement.appendChild(li);
    });
    console.log('Rank tooltip populated');
  }

  // Weekly Totals
  const currentWeekActivities = stravaData.activities.filter(activity => {
    const activityDate = new Date(activity.start_date);
    const today = new Date();
    const oneWeekAgo = new Date();
    oneWeekAgo.setDate(today.getDate() - 7);
    return activityDate >= oneWeekAgo && activityDate <= today;
  });

  console.log(`Found ${currentWeekActivities.length} activities in the past week`);

  const weeklyTotals = {
    hours: currentWeekActivities.reduce((sum, activity) => sum + (activity.duration / 3600), 0),
    distance: currentWeekActivities.reduce((sum, activity) => sum + activity.distance, 0),
    elevation: currentWeekActivities.reduce((sum, activity) => sum + activity.total_elevation_gain, 0),
    calories: currentWeekActivities.reduce((sum, activity) => sum + (activity.kilojoules || 0), 0),
  };

  console.log('Weekly Totals:', weeklyTotals);

  // Get Lifetime Stats
  const lifetimeStats = getLifetimeStats(stravaData.totals, weeklyTotals);
  console.log('Lifetime Stats:', lifetimeStats);

  // Update Lifetime Stats Section
  const distanceValueElement = document.getElementById('distance-value');
  const distanceWeekGainElement = document.getElementById('distance-week-gain');
  const elevationValueElement = document.getElementById('elevation-value');
  const elevationWeekGainElement = document.getElementById('elevation-week-gain');
  const caloriesValueElement = document.getElementById('calories-value');
  const caloriesWeekGainElement = document.getElementById('calories-week-gain');

  if (!distanceValueElement || !distanceWeekGainElement || !elevationValueElement || !elevationWeekGainElement || !caloriesValueElement || !caloriesWeekGainElement) {
    console.error('One or more lifetime stats DOM elements are missing.');
  } else {
    distanceValueElement.textContent = `${lifetimeStats.distance.icons} 🚴‍♂️`;
    distanceWeekGainElement.textContent = `+${lifetimeStats.distance.weekGain} this week`;

    elevationValueElement.textContent = `${lifetimeStats.elevation.icons} 🏔️`;
    elevationWeekGainElement.textContent = `+${lifetimeStats.elevation.weekGain} this week`;

    caloriesValueElement.textContent = `${lifetimeStats.calories.icons} 🍕`;
    caloriesWeekGainElement.textContent = `+${lifetimeStats.calories.weekGain} this week`;
  }

  // Update Weekly Stats
  const weeklyHoursElement = document.getElementById('weekly-hours');
  const weeklyDistanceElement = document.getElementById('weekly-distance');
  const weeklyElevationElement = document.getElementById('weekly-elevation');
  const weeklyCaloriesElement = document.getElementById('weekly-calories');

  if (!weeklyHoursElement || !weeklyDistanceElement || !weeklyElevationElement || !weeklyCaloriesElement) {
    console.error('One or more weekly stats DOM elements are missing.');
  } else {
    // Prevent NaN by checking if totals.hours is a number
    weeklyHoursElement.textContent = isNaN(weeklyTotals.hours) ? '0.0 hrs' : `${weeklyTotals.hours.toFixed(1)} hrs`;
    weeklyDistanceElement.textContent = isNaN(weeklyTotals.distance) ? '0.0 km' : `${(weeklyTotals.distance / 1000).toFixed(1)} km`;
    weeklyElevationElement.textContent = isNaN(weeklyTotals.elevation) ? '0 m' : `${weeklyTotals.elevation} m`;
    weeklyCaloriesElement.textContent = isNaN(weeklyTotals.calories) ? '0 kcal' : `${weeklyTotals.calories} kcal`;
  }

  console.log('Dashboard rendering complete');

  // Add Event Listeners for Tooltips
  addTooltipListeners();
}
function calculateRank(totalHours) {
  console.log(`Calculating rank for total hours: ${totalHours}`);
  let currentRank = rankConfig[0];
  let nextRank = rankConfig[1];

  for (let i = 0; i < rankConfig.length; i++) {
    if (totalHours >= rankConfig[i].minPoints) {
      currentRank = rankConfig[i];
      nextRank = rankConfig[i + 1] || rankConfig[i]; // If at top rank
    } else {
      break;
    }
  }

  // Calculate progress percentage
  const pointsIntoCurrentRank = totalHours - currentRank.minPoints;
  const pointsBetweenRanks = nextRank.minPoints - currentRank.minPoints;
  const progressPercent = pointsBetweenRanks > 0 ? (pointsIntoCurrentRank / pointsBetweenRanks) * 100 : 100;

  console.log('Calculated Rank Info:', {
    currentRank,
    nextRank,
    progressPercent,
    pointsIntoCurrentRank,
    pointsBetweenRanks,
  });

  return {
    currentRank,
    nextRank,
    progressPercent,
    currentPoints: totalHours,
    // Adjust 'nextRank.minPoints' as needed based on your ranking logic
  };
}

function getLifetimeStats(totals, weeklyTotals) {
  console.log('Calculating lifetime stats');
  const stats = {};

  // Distance
  const totalDistanceIcons = Math.floor(totals.distance / 100000); // 100km per icon
  const weeklyDistanceIcons = Math.floor(weeklyTotals.distance / 100000);
  stats.distance = { icons: totalDistanceIcons, weekGain: weeklyDistanceIcons };

  // Elevation
  const totalElevationGems = Math.floor(totals.elevation / 1000); // 1000m per gem
  const weeklyElevationGems = Math.floor(weeklyTotals.elevation / 1000);
  stats.elevation = { icons: totalElevationGems, weekGain: weeklyElevationGems };

  // Calories (Pizzas)
  const totalPizzas = Math.floor(totals.calories / 1000); // 1000kcal per pizza
  const weeklyPizzas = Math.floor(weeklyTotals.calories / 1000);
  stats.calories = { icons: totalPizzas, weekGain: weeklyPizzas };

  console.log('Lifetime Stats Calculated:', stats);
  return stats;
}

// Rank System Configuration
const rankConfig = [
  { name: 'Bronze 3', emoji: '🥉', minPoints: 0 },
  { name: 'Bronze 2', emoji: '🥉', minPoints: 50 },
  { name: 'Bronze 1', emoji: '🥉', minPoints: 100 },
  { name: 'Silver 3', emoji: '🥈', minPoints: 150 },
  { name: 'Silver 2', emoji: '🥈', minPoints: 200 },
  { name: 'Silver 1', emoji: '🥈', minPoints: 250 },
  { name: 'Gold 3', emoji: '🥇', minPoints: 300 },
  { name: 'Gold 2', emoji: '🥇', minPoints: 350 },
  { name: 'Gold 1', emoji: '🥇', minPoints: 400 },
  { name: 'Platinum 3', emoji: '🏆', minPoints: 450 },
  { name: 'Platinum 2', emoji: '🏆', minPoints: 500 },
  { name: 'Platinum 1', emoji: '🏆', minPoints: 550 },
  { name: 'Diamond 3', emoji: '💎', minPoints: 600 },
  { name: 'Diamond 2', emoji: '💎', minPoints: 650 },
  { name: 'Diamond 1', emoji: '💎', minPoints: 700 },
  { name: 'Master 3', emoji: '🔥', minPoints: 750 },
  { name: 'Master 2', emoji: '🔥', minPoints: 800 },
  { name: 'Master 1', emoji: '🔥', minPoints: 850 },
  { name: 'Grandmaster 3', emoji: '🚀', minPoints: 900 },
  { name: 'Grandmaster 2', emoji: '🚀', minPoints: 950 },
  { name: 'Grandmaster 1', emoji: '🚀', minPoints: 1000 },
  { name: 'Challenger', emoji: '🌟', minPoints: 1050 },
];

// Function to add event listeners for rank overview popup
function addRankOverviewEventListeners() {
  const rankContainer = document.getElementById('progress-container');
  const currentRankTitle = document.getElementById('current-rank');

  if (rankContainer && currentRankTitle) {
    rankContainer.addEventListener('click', toggleTooltip);
    currentRankTitle.addEventListener('click', toggleTooltip);
  } else {
    console.error('Rank container or current rank title element is missing.');
  }
}

function toggleTooltip() {
  const tooltip = document.getElementById('rank-tooltip');
  if (tooltip) {
    tooltip.style.display = tooltip.style.display === 'block' ? 'none' : 'block';
  } else {
    console.error('Rank tooltip element is missing.');
  }
}

function addTooltipListeners() {
  // Tooltip for Rank Section
  const rankContainer = document.getElementById('progress-container');
  const rankTooltip = document.getElementById('rank-tooltip');

  rankContainer.addEventListener('mouseenter', () => {
    rankTooltip.style.display = 'block';
  });

  rankContainer.addEventListener('mouseleave', () => {
    rankTooltip.style.display = 'none';
  });

  // Tooltip for Achievements
  const achievementIcons = document.querySelectorAll('.gem-icon, .pizza-icon, .distance-icon');
  achievementIcons.forEach(icon => {
    icon.addEventListener('mouseenter', () => {
      const title = icon.getAttribute('title');
      showTooltip(icon, title);
    });

    icon.addEventListener('mouseleave', () => {
      hideTooltip();
    });
  });
}

function showTooltip(element, text) {
  let tooltip = document.getElementById('achievement-tooltip');
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.id = 'achievement-tooltip';
    tooltip.style.position = 'absolute';
    tooltip.style.backgroundColor = '#fff';
    tooltip.style.color = '#333';
    tooltip.style.padding = '10px';
    tooltip.style.borderRadius = '5px';
    tooltip.style.boxShadow = '0 2px 6px rgba(0,0,0,0.2)';
    tooltip.style.fontSize = '14px';
    tooltip.style.zIndex = '1000';
    document.body.appendChild(tooltip);
  }
  tooltip.textContent = text;
  const rect = element.getBoundingClientRect();
  tooltip.style.top = `${rect.top - 40}px`;
  tooltip.style.left = `${rect.left + rect.width / 2}px`;
  tooltip.style.transform = 'translateX(-50%)';
  tooltip.style.display = 'block';
}

function hideTooltip() {
  const tooltip = document.getElementById('achievement-tooltip');
  if (tooltip) {
    tooltip.style.display = 'none';
  }
}


// Initialize dashboard by fetching the first page of activities
document.addEventListener('DOMContentLoaded', () => {
  fetchStravaData(currentPage, perPage);

  populateCompareSelect();
  const menuToggle = document.getElementById('menu-toggle');
  const menuClose = document.getElementById('menu-close');
  const compareSelect = document.getElementById('compare-user-select');
  const compareInputs = document.getElementById('compare-inputs');
  const compareLoad = document.getElementById('compare-load');
  const compareClear = document.getElementById('compare-clear');

  if (menuToggle) {
    menuToggle.addEventListener('click', () => toggleMenu(true));
  }
  if (menuClose) {
    menuClose.addEventListener('click', () => toggleMenu(false));
  }
  if (compareSelect && compareInputs) {
    compareSelect.addEventListener('change', () => {
      compareInputs.style.display = compareSelect.value === 'custom' ? 'block' : 'none';
    });
    compareInputs.style.display = compareSelect.value === 'custom' ? 'block' : 'none';
  }
  if (compareLoad) {
    compareLoad.addEventListener('click', handleCompareLoad);
  }
  if (compareClear) {
    compareClear.addEventListener('click', handleCompareClear);
  }
});
