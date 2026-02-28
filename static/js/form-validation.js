/**
 * Client-side form validation — mirrors backend validation rules.
 * Shows error messages in red below each input field.
 */
(function() {
  'use strict';

  var rules = {
    'name': {
      required: true,
      minLength: 2,
      maxLength: 100,
      message: 'Name is required (2-100 characters)'
    },
    'employee_id': {
      required: true,
      pattern: /^[A-Z]+-\d{4}$/,
      message: 'Employee ID must be in format CODE-0001'
    },
    'home_zone': {
      required: true,
      message: 'Home zone is required'
    },
    'department': {
      required: true,
      message: 'Department is required'
    },
    'primary_transport': {
      required: true,
      message: 'Transport mode is required'
    },
    'carpool_seats': {
      min: 0,
      max: 6,
      message: 'Carpool seats must be between 0 and 6'
    }
  };

  function validateField(input) {
    var name = input.name;
    var value = input.value.trim();
    var rule = rules[name];
    if (!rule) return true;

    var errorEl = input.parentElement.querySelector('.form-error');
    var valid = true;

    if (rule.required && !value) {
      valid = false;
    } else if (rule.minLength && value.length < rule.minLength) {
      valid = false;
    } else if (rule.maxLength && value.length > rule.maxLength) {
      valid = false;
    } else if (rule.pattern && !rule.pattern.test(value)) {
      valid = false;
    } else if (rule.min !== undefined && Number(value) < rule.min) {
      valid = false;
    } else if (rule.max !== undefined && Number(value) > rule.max) {
      valid = false;
    }

    if (!valid) {
      input.classList.add('is-invalid');
      if (errorEl) {
        errorEl.textContent = rule.message;
        errorEl.classList.add('visible');
      }
    } else {
      input.classList.remove('is-invalid');
      if (errorEl) {
        errorEl.classList.remove('visible');
      }
    }
    return valid;
  }

  function validateForm(form) {
    var inputs = form.querySelectorAll('input, select, textarea');
    var allValid = true;
    inputs.forEach(function(input) {
      if (!validateField(input)) allValid = false;
    });
    return allValid;
  }

  // Attach real-time validation on blur
  function initFormValidation(formSelector) {
    var form = document.querySelector(formSelector || 'form');
    if (!form) return;

    var inputs = form.querySelectorAll('input, select, textarea');
    inputs.forEach(function(input) {
      input.addEventListener('blur', function() { validateField(this); });
      input.addEventListener('input', function() {
        if (this.classList.contains('is-invalid')) validateField(this);
      });
    });

    form.addEventListener('submit', function(e) {
      if (!validateForm(form)) {
        e.preventDefault();
        // Scroll to first error
        var first = form.querySelector('.is-invalid');
        if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  }

  window.FormValidation = {
    init: initFormValidation,
    validate: validateField,
    validateForm: validateForm
  };
})();
